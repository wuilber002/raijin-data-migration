#!/usr/bin/env bash
set -euo pipefail

# OCI images can expose the complete boot disk while preserving the image's
# original, small LVM partition. Give Raijin, PostgreSQL, logs and releases all
# free extents in the root volume group. A later bootstrap is safe: it finds no
# free extents and therefore does not change the logical volume again.

for command in findmnt dmsetup lvs pvs vgs growpart pvresize lvextend udevadm; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required command is unavailable: $command" >&2
    exit 1
  }
done

root_source="$(findmnt -n -o SOURCE /)"
root_mapper="$(dmsetup splitname -c --noheadings -o vg_name,lv_name "$root_source" | xargs)"
root_mapping="${root_mapper##*/}"
root_vg="${root_mapping%%:*}"
root_lv_name="${root_mapping#*:}"
[[ -n "$root_vg" && -n "$root_lv_name" && "$root_mapping" == *:* ]] || {
  echo "Cannot determine the root logical volume" >&2
  exit 1
}
root_lv="/dev/$root_vg/$root_lv_name"

# Resolve the PV through LVM instead of assuming /dev/sda3. This keeps the
# expansion compatible with OCI shapes that expose a different device name.
root_pv="$(pvs --noheadings -o pv_name,vg_name | awk -v vg="$root_vg" '$2 == vg { print $1; exit }')"
[[ -b "$root_pv" ]] || { echo "Cannot determine the root physical volume" >&2; exit 1; }
root_pv_block_name="$(basename "$root_pv")"
parent_disk_name="$(basename "$(readlink -f "/sys/class/block/$root_pv_block_name/..")")"
partition_number="$(<"/sys/class/block/$root_pv_block_name/partition")"
[[ -n "$parent_disk_name" && -n "$partition_number" ]] || {
  echo "The root physical volume is not a growable disk partition: $root_pv" >&2
  exit 1
}

if growpart_output="$(growpart "/dev/$parent_disk_name" "$partition_number" 2>&1)"; then
  printf '%s\n' "$growpart_output"
elif [[ "$growpart_output" == *"NOCHANGE"* ]]; then
  # growpart uses a non-zero status when the partition already fills the disk.
  # That is normal on every bootstrap after the first expansion.
  printf '%s\n' "$growpart_output"
else
  printf '%s\n' "$growpart_output" >&2
  exit 1
fi
udevadm settle
pvresize "$root_pv"

free_extents="$(vgs --noheadings -o vg_free_count "$root_vg" | tr -cd '0-9')"
if [[ "$free_extents" =~ ^[1-9][0-9]*$ ]]; then
  lvextend -l +100%FREE "$root_lv"
  case "$(findmnt -n -o FSTYPE /)" in
    xfs) xfs_growfs / ;;
    ext4) resize2fs "$root_lv" ;;
    *) echo "Unsupported root filesystem: $(findmnt -n -o FSTYPE /)" >&2; exit 1 ;;
  esac
fi

echo "Raijin root filesystem is ready (all free extents allocated)."

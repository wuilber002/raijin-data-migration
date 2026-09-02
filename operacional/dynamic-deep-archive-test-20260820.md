# Teste Deep Archive dinâmico — 2026-08-20

## Recursos preparados

- Conta AWS: `056033527878`
- Bucket de origem: `s3-raijin-dynamic-archive-20260820`
- Prefixo: `linux-2.6.12-rc2/`
- Objetos: `17.291`
- Tamanho: `196.939.720 bytes`
- Classe: `DEEP_ARCHIVE`
- Source Raijin: `dynamic-deep-archive-20260820` (ID 6)
- Conexão: `aws-trial-fausto` (ID 1)
- Destino OCI: `bucket-S3-Destination`

O objeto histórico sob `linux-2.6.12-rc2/raijin-tests/` foi excluído da cópia.

## IAM temporário aplicado

Policies inline, estritas ao bucket/prefixo de teste:

- `s3-oci-migration-role`: `raijin-dynamic-archive-test-read`
- `s3-oci-batch-restore-role`: `raijin-dynamic-archive-test-restore`

## Próximo passo controlado

1. A configuração `raijin-dynamic-deep-archive-csv` entrega diariamente um S3 Inventory CSV.GZ em `raijin-inventory/`, filtrado para `linux-2.6.12-rc2/`; a primeira entrega pode levar até 48 horas.
2. Quando o arquivo estiver disponível, use **Discovery → Usar arquivo de inventário** para importá-lo na source ID 6 e valide `17.291` objetos, sem executar ListObjectsV2.
3. No Raijin, execute o pré-check da conexão `aws-trial-fausto`.
4. Crie waves dinâmicas sem agendamento; avalie a prévia e o histórico inicial.
5. Habilite Pipeline dinâmico somente antes do teste de restore aprovado.

## Cleanup, após aprovação de encerramento

```bash
aws iam delete-role-policy --role-name s3-oci-migration-role --policy-name raijin-dynamic-archive-test-read
aws iam delete-role-policy --role-name s3-oci-batch-restore-role --policy-name raijin-dynamic-archive-test-restore
aws s3api delete-bucket-inventory-configuration --bucket s3-raijin-dynamic-archive-20260820 --id raijin-dynamic-deep-archive-csv --region sa-east-1
aws s3api delete-bucket-policy --bucket s3-raijin-dynamic-archive-20260820 --region sa-east-1
aws s3 rm s3://s3-raijin-dynamic-archive-20260820 --recursive
aws s3api delete-bucket --bucket s3-raijin-dynamic-archive-20260820 --region sa-east-1
```

Não remova o bucket enquanto houver restore, retenção temporária ou auditoria em andamento.

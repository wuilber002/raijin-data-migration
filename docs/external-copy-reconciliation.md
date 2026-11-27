# Reconciliação de cópias externas no OCI

Uma source AWS já copiada por rclone não precisa de um cadastro especial.
Cadastre a rota AWS → OCI normalmente, execute o discovery AWS e então use
**Validar destino OCI**.

## Resultado da validação

- Para objetos ainda sem wave, a mesma chave de destino e o mesmo tamanho no
  OCI são evidência suficiente para adoção. O objeto passa a
  `PRESENT_IN_DESTINATION` com evidência `OCI_PREEXISTING`; ele não é contado
  nem apresentado como transferência feita pelo Raijin.
- Objetos que já foram associados a uma wave ou transferidos pelo Raijin
  continuam exigindo os metadados imutáveis de proveniência gravados no upload.
  Isso detecta substituição de um objeto sob a mesma chave e tamanho.
- Se todos os objetos do discovery forem encontrados sem divergência, a source
  fica `DONE`. Nenhuma wave, restore ou transferência é criada.
- Itens ausentes ou com tamanho divergente permanecem `DISCOVERED` e são os
  únicos elegíveis para waves futuras.

## Limite da evidência

Para uma cópia externa sem checksum comum entre AWS e OCI, chave + tamanho
prova cobertura e compatibilidade de tamanho, mas não igualdade criptográfica
de conteúdo. Use auditoria SHA-256 adicional quando essa garantia for exigida.

O CSV de inventário inclui `state`, `delivery_evidence` e
`delivery_evidence_at`, permitindo distinguir `OCI_PREEXISTING` de
`OCI_ACCEPTED` (transferido pelo Raijin).

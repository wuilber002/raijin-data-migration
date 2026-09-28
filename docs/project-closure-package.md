# Pacote de encerramento do projeto

O **Pacote de encerramento** é o documento formal de entrega de uma migração.
Ele pertence ao projeto e consolida todas as sources, inclusive as desativadas.
O **Resultado final** disponível em cada source continua sendo uma ferramenta
operacional e não substitui esse pacote.

## Fluxo de emissão

1. Selecione o projeto em **Migrations**.
2. Abra **Pacote de encerramento**.
3. Revise os gates e bloqueios. Se o destino ainda não estiver
   validado, execute **Validar destino OCI** na source. Essa verificação
   percorre todas as páginas e consulta o metadata de cada objeto; na topologia
   LOCAL o gateway mantém essa ação explícita aberta por até dez minutos.
4. Use **Baixar prévia PDF** para conferência. A prévia possui indicação
   explícita de que o projeto ainda não foi encerrado e não cria revisão.
5. Quando todos os gates estiverem aprovados, clique em **Emitir pacote final**.
6. Baixe o PDF para o cliente e o ZIP para guarda/auditoria técnica.

A primeira emissão cria `R1`. Uma nova emissão exige motivo, cria `R2`, `R3`
etc. e nunca altera as revisões anteriores.

## Gates obrigatórios

- Todas as sources precisam possuir discovery final concluído e inventário.
- Todos os objetos atuais precisam estar entregues e possuir evidência de
  integridade aceita pelo OCI.
- Nenhum objeto pode permanecer em falha.
- Todas as waves precisam estar concluídas.
- Não pode haver tarefa, retry, lease ou item da lane ainda pendente.
- A reconciliação do destino deve estar `VALID` e ter sido executada depois do
  último discovery e da última entrega de cada source.

Falhas nesses gates não podem ser convertidas em ressalvas. A auditoria
profunda é totalmente opcional: não executá-la não cria gate, aviso, ressalva
ou mudança de status. Sources desativadas continuam identificadas no escopo.
Tarifas e estimativas de custo pertencem exclusivamente à interface
operacional e nunca entram no pacote de encerramento.

## Conteúdo

O PDF contém identificação, resumo executivo, escopo, resultado por source,
integridade, desempenho e declaração de encerramento. O
ZIP contém:

```text
relatorio-final.pdf
manifest.json
project-summary.json
sources.csv
waves.csv
inventory.csv
destination-validation.csv
exceptions.csv
checksums.sha256
```

`manifest.json` informa schema, ID, revisão, aplicação e SHA-256/tamanho de
cada evidência técnica. O hash exato desse manifesto aparece no PDF.
`checksums.sha256` permite validar também o PDF e o próprio manifesto. O header
`X-Content-SHA256` dos downloads informa o hash do artefato persistido.

## Imutabilidade e proteção

Snapshot, PDF e ZIP são persistidos no PostgreSQL. Um download posterior serve
os bytes originais e não recalcula métricas. A emissão é auditada por evento e
revisões concorrentes são protegidas pela unicidade de projeto/revisão.

O pacote não inclui credenciais, secrets nem configuração privada do host. As
células CSV iniciadas por caracteres de fórmula são neutralizadas para evitar
execução ao abrir o documento em planilhas.

O snapshot utiliza somente dados persistidos pelo Raijin e os contratos
públicos dos provedores AWS e OCI. Não utiliza contratos, tempos ou metadados
internos de simuladores. Todos os timestamps do snapshot técnico usam UTC.

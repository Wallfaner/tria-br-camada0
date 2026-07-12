# Pasta de teste da Camada 0

Lotes TISS sintéticos para exercitar o saneador (`../camada0_extrator.py`) e o
painel (`../painel_camada0.html`). Dados 100% fictícios, gerados por
`../gerar_xml_teste.py` com seed fixa = 42 — reproduzíveis e livres para
redistribuição (licença MIT).

Cada lote foi contaminado de propósito com as anomalias reais do faturamento:
- guias sem datas de faturamento (viram `los = NaN`, não imputadas);
- valores monetários ilegíveis (ex.: `R$ 1.200,00` — rejeitados);
- guias sem `numeroGuiaPrestador` (desviadas à fila de auditoria);
- reapresentações duplicadas (purgadas por `keep=last`);
- um arquivo XML truncado (`*_corrompido.xml`, rejeitado inteiro).

Arraste estes arquivos para o `painel_camada0.html` ou rode o extrator sobre a
pasta para ver o fluxo completo da Camada 0.

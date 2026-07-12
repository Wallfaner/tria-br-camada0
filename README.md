# TRIA-BR — Códigos da Camada 0

Material de código que acompanha o livro **_A Conta Invisível — Inteligência
artificial, auditoria médica e os bilhões que o Brasil perde sem conseguir
medir_** (Wallace Faner Custódio Anselmo, Edição Ampliada, 2026).

Este repositório contém a **Camada 0 (Saneamento e Ingestão)** do framework
**TRIA-BR** — Triagem de Risco Inteligente para Auditoria — descrita no
Apêndice C.0 do livro. A Camada 0 transforma o fluxo bruto e hostil de guias
TISS (XML) da saúde suplementar em uma matriz matemática limpa, pronta para o
motor de regras (Camada 1) e o classificador de risco (Camada 2).

> O princípio central: a Camada 0 **não disfarça** a sujeira do faturamento —
> ela a **rotula, isola e preserva como `NaN`**, para que os algoritmos a
> jusante nunca aprendam padrões falsos a partir de valores imputados às cegas.

## Conteúdo

| Arquivo | O que é |
|---|---|
| [`camada0_extrator.py`](camada0_extrator.py) | O saneador de produção: extração em fluxo (`iterparse`), chave primária composta com deduplicação, anomalias rotuladas por flags e simetria de variáveis com a Camada 2. |
| [`painel_camada0.html`](painel_camada0.html) | Painel interativo que replica o extrator em JavaScript e roda **inteiramente no navegador** — nenhum dado sai da máquina. Mostra o fluxo de saneamento em tempo real e a análise estatística da matriz limpa. |
| [`gerar_xml_teste.py`](gerar_xml_teste.py) | Gerador de lotes TISS sintéticos (seed 42) contaminados com as anomalias reais do faturamento. |
| [`xml_teste/`](xml_teste/) | Lotes sintéticos prontos para arrastar no painel ou processar com o extrator. |
| [`apendice_C0_saneador.md`](apendice_C0_saneador.md) | O texto completo do Apêndice C.0 — a fundamentação metodológica da Camada 0. |

## Como usar

### Painel no navegador (sem instalar nada)

**▶ Abra o painel direto no navegador (GitHub Pages):**
https://wallfaner.github.io/tria-br-camada0/painel_camada0.html

Ou baixe `painel_camada0.html` e abra localmente. Clique em **"Processar lote
sintético (seed = 42)"** — ou arraste os arquivos de `xml_teste/` (ou suas
próprias guias TISS) para a área de upload. Todo o processamento é local.

### Extrator em Python

```bash
python3 gerar_xml_teste.py        # cria xml_teste/ com 6 lotes sintéticos
python3 -c "from camada0_extrator import extrair_tiss_producao; \
           df, erros = extrair_tiss_producao('xml_teste'); print(df.head())"
```

Requer `pandas`. O extrator devolve dois DataFrames: a matriz saneada (contas
prontas para triagem) e a fila de rejeição (registros desviados para auditoria
de dados — nada é descartado em silêncio).

## Nota sobre dados

Todos os XML deste repositório são **100% sintéticos** (personagens e valores
fictícios, seed fixa). Nenhuma guia real de paciente é distribuída aqui, em
respeito à LGPD. Antes de processar guias reais, opere sempre dentro do
perímetro de governança da instituição, conforme descrito no capítulo sobre
LGPD do livro.

## Licença

[MIT](LICENSE) © 2026 Wallace Faner Custódio Anselmo.

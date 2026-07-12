# APÊNDICE C.0 — O SANEADOR DE DADOS (CAMADA 0)

## A engenharia invisível: blindagem e vetorização do caos

O maior cemitério de projetos de inteligência artificial aplicada à auditoria médica no Brasil é a subestimação da etapa de ingestão. O padrão TISS (Troca de Informações na Saúde Suplementar), estabelecido pela ANS, é um ecossistema complexo e, na prática, as guias XML trafegam com omissões crônicas, preenchimentos incorretos e variações de leiaute entre versões do padrão.

A engenharia de dados na saúde suplementar não tolera aproximações. Quando uma prova de conceito baseada em dados sintéticos é transposta para a realidade operacional de hospitais e operadoras, pequenos desvios de modelagem ou falhas na interpretação dos esquemas XML (XSD) transformam soluções promissoras em sistemas instáveis ou — pior — em geradores silenciosos de dados corrompidos. Se o motor determinístico (Camada 1) ou o modelo de aprendizado de máquina (Camada 2) receberem dados imputados às cegas ou eivados de anomalias de digitação, o sistema produzirá falsos alertas e perderá aquilo que não recupera: a credibilidade dos auditores médicos. A Camada 0 não deve ocultar a sujeira do faturamento; deve rotulá-la, isolá-la e entregar às camadas seguintes uma matriz matemática honesta.

Para garantir a viabilidade técnica em produção sob volumes continentais de guias, o extrator definitivo adota cinco preceitos de arquitetura de dados:

**1. Adesão estrita ao XSD real — com tolerância a versões.** Substitui-se o mapeamento ingênuo pelas tags oficiais da Guia de Resumo de Internação. O diagnóstico principal é extraído do primeiro nó `diagnosticoCID` — e, como o leiaute desse nó varia entre versões do TISS (em parte delas o código vem direto no texto; em outras, num filho `codigoDiagnostico`), o extrator aceita ambos. Os valores financeiros são localizados na hierarquia correta (`valorTotal/valorTotalGeral` e `valorTotal/valorOPME`). O tempo de permanência não é lido de uma tag de diárias — ela não existe na guia —, mas calculado pelo delta temporal entre `dataInicioFaturamento` e `dataFinalFaturamento`. Pelo mesmo motivo, a competência da conta não é buscada numa tag fantasma: é derivada do ano-mês da data final de faturamento.

**2. Fluxo em vez de memória (`ET.iterparse`).** Arquivos de lote massivos esgotam a memória RAM se carregados integralmente com `ET.parse()`. A análise baseada em eventos processa cada guia e a descarta da memória imediatamente após a extração, permitindo que o pipeline percorra gigabytes de faturamento em hardware modesto.

**3. Chave primária composta e deduplicação.** O número da guia isolado (`numeroGuiaPrestador`) não garante unicidade ao longo de múltiplos prestadores e competências — e guias reapresentadas chegam em lotes diferentes. O pipeline constrói a chave `registroANS + competência + número da guia` e aplica uma purga ativa de duplicidades antes do treino, mantendo a última versão enviada (a reapresentação prevalece sobre a original). Um detalhe traiçoeiro: uma tag *presente porém vazia* devolve texto vazio, não o valor-padrão do extrator — por isso a normalização trata os dois casos com o mesmo sentinela, e guias sem identificação são desviadas para a fila de erros em vez de entrarem no treino com chave truncada.

**4. Anomalias rotuladas, nunca disfarçadas.** Em vez de imputar valores arbitrários — que geram outliers artificiais na diária média e ensinam padrões falsos ao modelo —, o extrator cria colunas de controle (`periodo_invalido`, `valor_ilegivel`) e codifica o dado ausente como `NaN`. Aqui há um encaixe metodológico preciso com o Apêndice C.1: o `HistGradientBoostingClassifier` trata valores ausentes **nativamente**, aprendendo para que lado enviar cada ausência em cada divisão da árvore. O pipeline, portanto, nunca precisa inventar números. Contas sem identificação ou sem valor legível não são "consertadas": são desviadas ao repositório de rejeição, que vira pauta da auditoria de dados — um subproduto de governança, não um lixo descartado.

**5. Simetria nominal com o modelo.** As colunas de saída (`los`, `n_itens`, `valor_diaria`, `pct_opme`) usam exatamente os nomes consumidos pelo classificador do Apêndice C.1, fechando o circuito do framework: o que a Camada 0 produz, a Camada 2 consome sem tradução.

```python
"""
TRIA-BR · Camada 0 — Saneador de Dados (Apêndice C.0)
Extrator de arquitetura industrial para guias TISS XML (Resumo de Internação).
Processamento em fluxo (iterparse), chave primária composta com deduplicação,
anomalias rotuladas por flags (nunca imputadas às cegas) e simetria nominal
com o classificador do Apêndice C.1. Licença MIT.
"""

import os
import datetime
import xml.etree.ElementTree as ET
import pandas as pd

# Namespace oficial da ANS — o maior ofensor na leitura de arquivos TISS
NS = {'ans': 'http://www.ans.gov.br/padroes/tiss/schemas'}


def _cid_principal(guia):
    """Diagnóstico principal, tolerante a variações de leiaute entre versões
    do TISS: em parte das versões o código vem no texto de diagnosticoCID;
    em outras, no filho codigoDiagnostico. O primeiro nó é o principal."""
    no = guia.find('.//ans:diagnosticoCID', NS)
    if no is None:
        return 'INDEFINIDO'
    if no.text and no.text.strip():
        return no.text.strip().upper()
    filho = no.find('.//ans:codigoDiagnostico', NS)
    if filho is not None and filho.text:
        return filho.text.strip().upper()
    return 'INDEFINIDO'


def _valor_monetario(guia, caminho):
    """Converte um campo monetário; devolve (valor, flag_ilegivel)."""
    bruto = guia.findtext(caminho, default='', namespaces=NS)
    try:
        return float(bruto), 0
    except ValueError:
        return 0.0, 1


def extrair_tiss_producao(diretorio_xml):
    """Lê todos os XML TISS de um diretório e devolve dois DataFrames:
    (contas saneadas prontas para as Camadas 1 e 2, registros rejeitados)."""
    dados_saneados = []
    logs_rejeicao = []

    for arquivo in sorted(os.listdir(diretorio_xml)):
        if not arquivo.lower().endswith('.xml'):
            continue
        caminho = os.path.join(diretorio_xml, arquivo)

        try:
            # iterparse processa o arquivo em fluxo: cada guia é lida,
            # extraída e descartada da RAM, permitindo gigabytes de lote
            # em hardware modesto — ET.parse carregaria o arquivo inteiro.
            for _, elem in ET.iterparse(caminho, events=('end',)):
                if not elem.tag.endswith('guiaResumoInternacao'):
                    continue

                # 1. Chave primária composta: o numeroGuiaPrestador sozinho
                # não é único entre prestadores e competências. A competência
                # é derivada da dataFinalFaturamento — não existe tag
                # "competencia" dentro da guia.
                # Tag ausente E tag presente-porém-vazia caem no sentinela:
                # findtext devolve '' quando o nó existe sem texto.
                reg_ans = (elem.findtext('.//ans:registroANS', default='',
                                         namespaces=NS) or '').strip() or 'SEM_REG'
                num_guia = (elem.findtext('.//ans:numeroGuiaPrestador', default='',
                                          namespaces=NS) or '').strip() or 'SEM_ID'

                # 2. Tempo de permanência (los) derivado por delta temporal —
                # a guia de resumo de internação não possui tag de diárias.
                dt_ini = elem.findtext('.//ans:dataInicioFaturamento',
                                       default='', namespaces=NS)
                dt_fim = elem.findtext('.//ans:dataFinalFaturamento',
                                       default='', namespaces=NS)
                los = float('nan')
                flag_periodo = 1
                competencia = '000000'
                try:
                    inicio = datetime.date.fromisoformat(dt_ini.strip())
                    fim = datetime.date.fromisoformat(dt_fim.strip())
                    if fim >= inicio:
                        los = max(1, (fim - inicio).days)
                        flag_periodo = 0
                    competencia = f'{fim.year:04d}{fim.month:02d}'
                except ValueError:
                    pass  # datas ausentes ou corrompidas: flag permanece 1

                id_conta = f'{reg_ans}_{competencia}_{num_guia}'

                # 3. Valores hierárquicos do bloco valorTotal (XSD real)
                valor_total, flag_valor = _valor_monetario(
                    elem, './/ans:valorTotal/ans:valorTotalGeral')
                valor_opme, _ = _valor_monetario(
                    elem, './/ans:valorTotal/ans:valorOPME')

                # 4. Vetorização dos procedimentos TUSS
                procedimentos = [
                    p.text.strip()
                    for p in elem.findall(
                        './/ans:procedimentoExecutado'
                        '//ans:codigoProcedimento', NS)
                    if p.text and p.text.strip()
                ]

                # 5. Features de risco: NaN em vez de imputação cega.
                # O HistGradientBoostingClassifier do Apêndice C.1 trata
                # ausências nativamente — o pipeline nunca inventa números.
                pct_opme = (valor_opme / valor_total) if valor_total > 0 else 0.0
                valor_diaria = (valor_total / los) if flag_periodo == 0 else float('nan')

                # 6. Filtragem ativa: sem identificação ou sem valor, a conta
                # não serve à triagem — vai para a fila de auditoria de dados.
                if num_guia == 'SEM_ID' or valor_total <= 0.0:
                    logs_rejeicao.append({
                        'arquivo': arquivo,
                        'id_provisorio': id_conta,
                        'motivo': ('Guia sem identificação' if num_guia == 'SEM_ID'
                                   else 'Valor total zerado ou ilegível'),
                    })
                else:
                    dados_saneados.append({
                        'id_conta': id_conta,
                        'cid_principal': _cid_principal(elem),
                        'procedimentos_tuss': procedimentos,
                        'n_itens': len(procedimentos),
                        'los': los,
                        'valor_total': round(valor_total, 2),
                        'valor_opme': round(valor_opme, 2),
                        'pct_opme': round(pct_opme, 4),
                        'valor_diaria': (round(valor_diaria, 2)
                                         if flag_periodo == 0 else valor_diaria),
                        'periodo_invalido': flag_periodo,
                        'valor_ilegivel': flag_valor,
                        'arquivo_origem': arquivo,
                    })

                elem.clear()  # libera a guia processada da memória

        except ET.ParseError:
            logs_rejeicao.append({'arquivo': arquivo, 'id_provisorio': 'N/A',
                                  'motivo': 'XML corrompido ou malformado'})
        except OSError as e:
            logs_rejeicao.append({'arquivo': arquivo, 'id_provisorio': 'N/A',
                                  'motivo': f'Falha de leitura: {e}'})

    df_saneado = pd.DataFrame(dados_saneados)
    df_erros = pd.DataFrame(logs_rejeicao)

    # Purga ativa de duplicidades: em reapresentações de lote, a última
    # versão enviada da guia prevalece sobre as anteriores.
    if not df_saneado.empty:
        antes = len(df_saneado)
        df_saneado = df_saneado.drop_duplicates(subset='id_conta', keep='last')
        purgadas = antes - len(df_saneado)
        if purgadas > 0:
            print(f'[GOVERNANÇA] {purgadas} guia(s) duplicada(s) removida(s) '
                  f'— reapresentação: última versão prevalece.')

    print(f'Extração concluída: {len(df_saneado)} contas prontas para triagem; '
          f'{len(df_erros)} registro(s) desviado(s) para auditoria de dados.')
    return df_saneado, df_erros
```

## O fechamento metodológico: da higienização à triagem

Com a Camada 0 validada sob condições extremas e o pipeline imune a dados corrompidos, a fundação estrutural do TRIA-BR está consolidada. A substituição de imputações arbitrárias (como preencher diárias ausentes com `1` ou valores ilegíveis com `0.0`) pelo uso do `NaN` (*Not a Number*) não é um mero detalhe de sintaxe em Python; é uma decisão metodológica fundamental para a auditoria em saúde.

Mascarar a ausência de dados introduz vieses invisíveis na distribuição estatística. Modelos avançados baseados em árvores de decisão, como o `HistGradientBoostingClassifier` utilizado na Camada 2, tratam valores faltantes de forma nativa: utilizam a própria ausência da informação como um nó de ramificação, transformando a "falta de dado" em um sinal preditivo valioso. Forçar o preenchimento artificial destruiria essa capacidade algorítmica, criando *outliers* artificiais (diárias subfaturadas irreais) que gerariam falsos positivos e exauririam a equipe médica.

Além disso, a implementação da chave primária composta (Registro ANS + Competência + Número da Guia) e a consequente purga de duplicidades atuam como a primeira linha de defesa contra o *data leakage* (vazamento de dados). Sem essa trava, guias reapresentadas após recurso de glosa entrariam duplicadas no treinamento da inteligência artificial, inflando artificialmente o peso de contas litigiosas no algoritmo.

A sujeira intrínseca ao padrão XML não foi ocultada; foi rotulada com *flags* de controle (`periodo_invalido`, `valor_ilegivel`) e isolada, garantindo total transparência sobre o porquê de certas guias não receberem o escore de risco. Como o dado ausente viaja como `NaN` até um classificador que o trata nativamente, a fronteira entre "o que o hospital informou" e "o que o pipeline supôs" permanece visível do início ao fim — condição necessária para a explicabilidade que a Camada 3 exige do sistema diante do auditor médico.

Com a matriz matemática saneada e estruturada, o terreno deixa a engenharia de dados e entra na lógica de negócios. O foco agora migra para a **Camada 1 (Motor de Regras Determinísticas)**. O próximo estágio da automação da auditoria consiste em abandonar os tetos estáticos e cruzar essa matriz limpa com limiares de alerta dinâmicos — balizados, por exemplo, pelo percentil 99 de custo por especialidade extraído diretamente do DATASUS —, garantindo que o filtro do óbvio atue com a mesma precisão do modelo de *machine learning*.

## Material digital: o painel de execução

Um livro impresso não executa código — mas o leitor pode. O material digital que acompanha esta edição inclui o **Painel de Execução da Camada 0** (`painel_camada0.html`): uma implementação interativa deste extrator que roda inteiramente no navegador, sem instalação e sem enviar um único byte para fora da máquina — a mesma postura de soberania de dados defendida no capítulo sobre LGPD, agora demonstrada em vez de apenas prometida.

O painel torna visível o que este apêndice descreve: a faixa de fluxo mostra, em tempo real, cada guia atravessando os quatro estágios (ingestão em fluxo, chave composta e deduplicação, rotulagem de anomalias, matriz saneada), com os desvios ramificados — rejeitadas, duplicatas purgadas, guias mantidas com flag. Abaixo, o histograma da diária média exibe a cauda direita que é a matéria-prima da Camada 1, e as tabelas comutáveis mostram a matriz final, a fila de rejeição e o log de governança linha a linha.

O leitor não precisa possuir guias TISS para experimentar. Há dois caminhos:

1. **O lote sintético embutido.** O botão *Processar lote sintético (seed = 42)* gera, no próprio navegador, cerca de 300 guias calibradas com as distribuições do Apêndice C.1 e contaminadas com as hostilidades reais do faturamento — guias sem datas, valores ilegíveis, guias sem identificação, reapresentações duplicadas e um arquivo XML truncado. A seed fixa garante que todo leitor veja exatamente os mesmos números.
2. **O gerador de arquivos.** O script `gerar_xml_teste.py` cria a pasta `xml_teste/` com seis lotes XML no padrão TISS, prontos para serem arrastados ao painel — ou processados diretamente pelo extrator deste apêndice. É também o ponto de partida para quem quiser editar os XML à mão e observar como o pipeline reage.

Quem tiver acesso a guias reais pode arrastá-las ao painel com a mesma tranquilidade: a leitura é integral e local, e nada é transmitido. Painel, extrator e gerador estão disponíveis no repositório de códigos do livro, sob licença MIT.

---

*Nota de reprodutibilidade: este extrator foi validado contra um conjunto de guias sintéticas hostis — lotes válidos em dois leiautes de `diagnosticoCID`, guia sem datas, valor monetário ilegível ("R$ 1.200,00"), guia sem identificação, XML truncado e reapresentação duplicada. Todos os desvios foram corretamente rotulados ou rejeitados, e a saída alimentou o `HistGradientBoostingClassifier` do Apêndice C.1 sem qualquer etapa de imputação. O pipeline foi validado também contra uma guia TISS 3.02.00 de estrutura real (dados fictícios), obtida de repositório público — teste que revelou uma armadilha ausente dos dados sintéticos: em guias de produção, cada procedimento e despesa carrega seu próprio `valorTotal` escalar, e apenas o caminho hierárquico `valorTotal/valorTotalGeral` distingue o bloco-resumo da guia. Dados hostis reais encontram o que dados sintéticos bem-comportados não encontram.*

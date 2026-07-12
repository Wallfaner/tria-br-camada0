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

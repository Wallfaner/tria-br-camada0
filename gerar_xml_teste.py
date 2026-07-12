"""
TRIA-BR · Gerador de lotes TISS sintéticos para teste da Camada 0.
Cria a pasta xml_teste/ com 6 lotes de guias de Resumo de Internação,
calibrados com as mesmas distribuições do Apêndice C.1 (seed fixa = 42)
e contaminados com as hostilidades reais do faturamento: guias sem datas,
valores ilegíveis, guias sem identificação, reapresentações duplicadas e
um arquivo XML corrompido. Nenhum dado real: 100% sintético. Licença MIT.

Uso:  python3 gerar_xml_teste.py
Depois arraste os arquivos de xml_teste/ para o painel_camada0.html,
ou rode o extrator do Apêndice C.0 sobre a pasta.
"""

import os
import random
import datetime

random.seed(42)

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'xml_teste')
os.makedirs(DIR, exist_ok=True)

NS = 'http://www.ans.gov.br/padroes/tiss/schemas'
CIDS = ['I21.0', 'S72.0', 'J18.9', 'K35.8', 'A41.9',
        'N39.0', 'C34.9', 'I63.9', 'O80', 'I50.0']
TUSS = ['31005497', '40304361', '30715016', '31602096', '31003079',
        '31101011', '40803104', '30912016', '41001010', '30213036']
MESES = ['2025-03', '2025-04', '2025-05']


def xml_guia(reg, num, cid, layout_b, ini, fim, total, opme, procs):
    if layout_b:  # variação de leiaute entre versões do TISS
        diag = (f'<ans:diagnosticoCID><ans:codigoDiagnostico>{cid}'
                f'</ans:codigoDiagnostico></ans:diagnosticoCID>')
    else:
        diag = f'<ans:diagnosticoCID>{cid}</ans:diagnosticoCID>'
    px = ''.join(
        f'<ans:procedimentoExecutado><ans:procedimento>'
        f'<ans:codigoProcedimento>{p}</ans:codigoProcedimento>'
        f'</ans:procedimento></ans:procedimentoExecutado>' for p in procs)
    datas = ''
    if ini:
        datas += f'<ans:dataInicioFaturamento>{ini}</ans:dataInicioFaturamento>'
    if fim:
        datas += f'<ans:dataFinalFaturamento>{fim}</ans:dataFinalFaturamento>'
    return (f'<ans:guiaResumoInternacao><ans:cabecalhoGuia>'
            f'<ans:registroANS>{reg}</ans:registroANS>'
            f'<ans:numeroGuiaPrestador>{num}</ans:numeroGuiaPrestador>'
            f'</ans:cabecalhoGuia>{datas}{diag}'
            f'<ans:procedimentosExecutados>{px}</ans:procedimentosExecutados>'
            f'<ans:valorTotal><ans:valorOPME>{opme}</ans:valorOPME>'
            f'<ans:valorTotalGeral>{total}</ans:valorTotalGeral>'
            f'</ans:valorTotal></ans:guiaResumoInternacao>')


def xml_lote(guias):
    return (f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<ans:mensagemTISS xmlns:ans="{NS}"><ans:loteGuias>'
            + ''.join(guias) + '</ans:loteGuias></ans:mensagemTISS>')


seq = 0
historico = []
resumo = []

for f in range(6):
    mes = MESES[f % len(MESES)]
    guias = []
    n_guias = random.randint(30, 45)
    for _ in range(n_guias):
        seq += 1
        num_guia = f'G{seq:05d}'
        los = max(1, round(random.gammavariate(2.0, 2.5)))
        dia_ini = random.randint(1, 20)
        ini = f'{mes}-{dia_ini:02d}'
        fim = (datetime.date.fromisoformat(ini)
               + datetime.timedelta(days=los)).isoformat()
        valor = min(400_000, max(800, random.lognormvariate(8.6, 0.9)))
        pct_opme = random.random() ** 3 * 0.6
        opme = valor * pct_opme
        n_itens = max(1, round(2 + random.gammavariate(1.6, 1.0) + los * 0.8))
        procs = [random.choice(TUSS) for _ in range(min(n_itens, 14))]
        cid = random.choice(CIDS)

        # hostilidades calibradas
        sem_datas = random.random() < 0.05
        ilegivel = random.random() < 0.025
        sem_id = random.random() < 0.015

        total_str = (f'R$ {valor:,.0f},00'.replace(',', '.')
                     if ilegivel else f'{valor:.2f}')
        guias.append(xml_guia(
            '312345', '' if sem_id else num_guia, cid,
            random.random() < 0.4,
            '' if sem_datas else ini, '' if sem_datas else fim,
            total_str, f'{opme:.2f}', procs))
        if not sem_id and not ilegivel:
            historico.append((num_guia, cid, ini, fim, valor, opme, procs))
        # 3%: reapresentação de guia anterior (mesma chave, valor corrigido)
        if len(historico) > 10 and random.random() < 0.03:
            h = random.choice(historico)
            guias.append(xml_guia('312345', h[0], h[1], False, h[2], h[3],
                                  f'{h[4]*0.93:.2f}', f'{h[5]*0.9:.2f}', h[6]))

    conteudo = xml_lote(guias)
    nome = f'lote_{mes.replace("-", "_")}_{f+1:02d}.xml'
    if f == 4:  # um arquivo deliberadamente corrompido (truncado)
        conteudo = conteudo[:400]
        nome = f'lote_{mes.replace("-", "_")}_{f+1:02d}_corrompido.xml'
    with open(os.path.join(DIR, nome), 'w', encoding='UTF-8') as arq:
        arq.write(conteudo)
    resumo.append((nome, len(guias)))

print(f'Pasta {DIR} criada com {len(resumo)} lotes:')
for nome, n in resumo:
    print(f'  {nome:40s} {n:3d} guia(s)')
print('Arraste esses arquivos para o painel_camada0.html '
      'ou rode o extrator do Apêndice C.0 sobre a pasta xml_teste/.')

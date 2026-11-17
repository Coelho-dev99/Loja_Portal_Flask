"""Geracao das planilhas Excel (.xlsx) do relatorio e dos clientes."""
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill

from app.status import ROTULOS
from app.util import formatar_fone

MOEDA = '"R$" #,##0.00'
DATA = "dd/mm/yyyy"
DATA_HORA = "dd/mm/yyyy hh:mm"
FONTE_CABECALHO = Font(bold=True, color="FFFFFF")
FUNDO_CABECALHO = PatternFill("solid", fgColor="5B2FC0")
NEGRITO = Font(bold=True)


def _escrever(ws, linha, coluna, valor, formato=None):
    """Escreve um valor. Texto vindo de clientes NUNCA vira formula."""
    celula = ws.cell(row=linha, column=coluna)
    if isinstance(valor, str):
        celula.value = ILLEGAL_CHARACTERS_RE.sub("", valor)
        celula.data_type = "s"  # texto puro: =, +, - ou @ no inicio nao executam nada
    elif isinstance(valor, Decimal):
        celula.value = float(valor)
    else:
        celula.value = valor
    if formato:
        celula.number_format = formato
    return celula


def _tabela(ws, linha_inicial, cabecalhos, linhas, formatos, total_de=()):
    """Cabecalho + linhas. `total_de` lista as colunas (0, 1, 2...) que ganham linha de total."""
    for j, titulo in enumerate(cabecalhos, start=1):
        c = _escrever(ws, linha_inicial, j, titulo)
        c.font = FONTE_CABECALHO
        c.fill = FUNDO_CABECALHO
        c.alignment = Alignment(vertical="center", wrap_text=True)

    atual = linha_inicial
    somas = {j: 0 for j in total_de}
    for valores in linhas:
        atual += 1
        for j, valor in enumerate(valores):
            _escrever(ws, atual, j + 1, valor, formatos[j])
            if j in somas and valor is not None:
                somas[j] += float(valor)

    if total_de and linhas:
        atual += 1
        _escrever(ws, atual, 1, "Total").font = NEGRITO
        for j, soma in somas.items():
            _escrever(ws, atual, j + 1, soma, formatos[j]).font = NEGRITO
    return atual


def _larguras(ws, larguras):
    for i, largura in enumerate(larguras, start=1):
        ws.column_dimensions[chr(64 + i)].width = largura


def _salvar(wb):
    arquivo = BytesIO()
    wb.save(arquivo)
    arquivo.seek(0)
    return arquivo


def relatorio_mensal(dados):
    mes, r = dados["mes"], dados["resumo"]
    wb = Workbook()

    # ---- Resumo ----
    ws = wb.active
    ws.title = "Resumo"
    _escrever(ws, 1, 1, f"Relatório de {mes['rotulo']}").font = Font(bold=True, size=14)
    _escrever(ws, 2, 1, "Conta como venda o pedido pago (ou em andamento, enviado ou concluído), no mês em que foi marcado como Pago.")
    linhas = [
        ("Pedidos vendidos", r["pedidos"], None),
        ("Peças vendidas", r["pecas"], None),
        ("Faturamento das peças", r["faturamento"], MOEDA),
        ("Frete cobrado", r["frete"], MOEDA),
        ("Total (peças + frete)", r["total"], MOEDA),
        ("Peças personalizadas sem valor definido", r["sem_valor"], None),
        ("Clientes novos no mês", dados["clientes_mes"]["novos"], None),
        ("Clientes que já tinham comprado antes", dados["clientes_mes"]["recorrentes"], None),
        ("Pedidos aguardando pagamento (agora)", r["aguardando"], None),
        ("Pedidos cancelados criados no mês", r["cancelados"], None),
    ]
    for i, (rotulo, valor, formato) in enumerate(linhas, start=4):
        _escrever(ws, i, 1, rotulo).font = NEGRITO
        _escrever(ws, i, 2, valor, formato)
    _larguras(ws, [44, 18])

    # ---- Pronta entrega ----
    ws = wb.create_sheet("Pronta entrega")
    _tabela(ws, 1, ["Produto", "Quantidade", "Total (R$)"],
            [(p["nome"], p["qtd"], p["total"]) for p in dados["produtos"]],
            [None, "0", MOEDA], total_de=(1, 2))
    ws.freeze_panes = "A2"
    _larguras(ws, [40, 14, 16])

    # ---- Personalizados por tipo ----
    ws = wb.create_sheet("Personalizados por tipo")
    _tabela(ws, 1, ["Tipo", "Peças", "Total (R$)", "Peças sem valor"],
            [(t["nome"], t["qtd"], t["total"], t["sem_valor"]) for t in dados["tipos"]],
            [None, "0", MOEDA, "0"], total_de=(1, 2, 3))
    ws.freeze_panes = "A2"
    _larguras(ws, [30, 10, 16, 16])

    # ---- Personalizados (detalhe) ----
    ws = wb.create_sheet("Personalizados (detalhe)")
    _tabela(ws, 1, ["Pedido", "Data da venda", "Cliente", "Tipo", "Descrição", "Qtd", "Valor unit. (R$)", "Subtotal (R$)"],
            [(i["pedido"], i["data_venda"], i["cliente"], i["tipo"], i["descricao"], i["quantidade"],
              i["valor_unitario"],
              i["quantidade"] * i["valor_unitario"] if i["valor_unitario"] is not None else None)
             for i in dados["personalizados"]],
            ["0", DATA, None, None, None, "0", MOEDA, MOEDA])
    ws.freeze_panes = "A2"
    _larguras(ws, [9, 14, 28, 16, 60, 6, 16, 16])
    for linha in ws.iter_rows(min_row=2, min_col=5, max_col=5):
        linha[0].alignment = Alignment(wrap_text=True, vertical="top")

    # ---- Pedidos do mes ----
    ws = wb.create_sheet("Pedidos do mês")
    _tabela(ws, 1, ["Pedido", "Data da venda", "Cliente", "Status", "Peças", "Valor das peças (R$)", "Frete (R$)", "Total (R$)"],
            [(p["id"], p["data_venda"], p["cliente"], ROTULOS.get(p["status"], p["status"]), p["pecas"],
              p["valor_pecas"], p["frete_valor"], p["valor_pecas"] + (p["frete_valor"] or 0))
             for p in dados["pedidos"]],
            ["0", DATA, None, None, "0", MOEDA, MOEDA, MOEDA], total_de=(4, 5, 6, 7))
    ws.freeze_panes = "A2"
    _larguras(ws, [9, 14, 30, 16, 8, 20, 14, 14])

    # ---- Clientes recorrentes ----
    ws = wb.create_sheet("Clientes recorrentes")
    _tabela(ws, 1, ["Cliente", "Instagram", "Telefone", "Pedidos", "Total gasto (R$)", "Primeira compra", "Última compra"],
            [(c["nome"], ("@" + c["instagram"]) if c["instagram"] else None, formatar_fone(c["telefone"]),
              c["pedidos"], c["total"], c["primeira"], c["ultima"]) for c in dados["recorrentes"]],
            [None, None, None, "0", MOEDA, DATA, DATA])
    ws.freeze_panes = "A2"
    _larguras(ws, [30, 22, 18, 10, 18, 16, 16])

    return _salvar(wb)


def lista_de_clientes(clientes):
    wb = Workbook()
    ws = wb.active
    ws.title = "Clientes"
    _tabela(ws, 1,
            ["Nome", "Telefone", "Instagram", "Cidade/UF", "Pedidos vendidos", "Total gasto (R$)",
             "Primeira compra", "Última compra", "Cadastrado em"],
            [(c["nome"], formatar_fone(c["telefone"]), ("@" + c["instagram"]) if c["instagram"] else None,
              c["cidade_uf"], c["pedidos"], c["total"], c["primeira"], c["ultima"], c["criado_em"])
             for c in clientes],
            [None, None, None, None, "0", MOEDA, DATA, DATA, DATA])
    ws.freeze_panes = "A2"
    _larguras(ws, [32, 18, 22, 22, 16, 18, 16, 16, 16])
    return _salvar(wb)

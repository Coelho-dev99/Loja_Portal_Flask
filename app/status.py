ROTULOS = {
    "aguardando_pagamento": "Aguardando pagamento",
    "pago": "Pago",
    "processando": "Processando",
    "enviado": "Enviado",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
}

# Para quais status cada pedido pode ir (voce muda manualmente no painel).
PROXIMOS = {
    "aguardando_pagamento": ["pago", "cancelado"],
    "pago": ["processando", "cancelado"],
    "processando": ["enviado", "cancelado"],
    "enviado": ["concluido"],
    "concluido": [],
    "cancelado": [],
}

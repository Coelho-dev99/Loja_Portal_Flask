ROTULOS = {
    "aguardando_dados": "Aguardando dados",
    "confirmado": "Confirmado",
    "pago": "Pago",
    "enviado": "Enviado",
    "entregue": "Entregue",
    "cancelado": "Cancelado",
}

# Para quais status cada pedido pode ir. O estoque e reservado quando o
# cliente envia os dados (aguardando_dados -> confirmado) e devolvido se o
# pedido for cancelado depois disso.
PROXIMOS = {
    "aguardando_dados": ["cancelado"],
    "confirmado": ["pago", "cancelado"],
    "pago": ["enviado", "cancelado"],
    "enviado": ["entregue", "cancelado"],
    "entregue": [],
    "cancelado": [],
}

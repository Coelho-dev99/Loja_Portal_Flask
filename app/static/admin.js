// Comportamentos do painel que antes ficavam dentro do HTML (onclick/onsubmit).
// Foram movidos para ca porque a politica de seguranca do site (CSP) nao
// permite codigo JavaScript escrito dentro dos atributos das tags.

// <form data-confirmar="Pergunta?"> pergunta antes de enviar.
// Opcional: data-confirmar-campo="status" data-confirmar-valor="cancelado"
// so pergunta quando aquele campo estiver com aquele valor.
document.addEventListener("submit", function (evento) {
  const form = evento.target;
  if (!form.matches || !form.matches("form[data-confirmar]")) return;

  const campo = form.dataset.confirmarCampo;
  if (campo && form.elements[campo] && form.elements[campo].value !== form.dataset.confirmarValor) {
    return;
  }
  if (!window.confirm(form.dataset.confirmar)) {
    evento.preventDefault();
  }
});

// <input data-selecionar> seleciona o texto inteiro ao clicar (para copiar o link).
document.addEventListener("click", function (evento) {
  const alvo = evento.target;
  if (alvo.matches && alvo.matches("input[data-selecionar]")) {
    alvo.select();
  }
});

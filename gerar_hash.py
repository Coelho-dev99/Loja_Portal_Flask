from getpass import getpass

from werkzeug.security import generate_password_hash

senha = getpass("Digite a senha do painel (nao aparece enquanto digita): ")
confirmacao = getpass("Repita a senha: ")

if senha != confirmacao:
    print("As senhas nao conferem. Rode de novo.")
elif len(senha) < 12:
    print("Use pelo menos 12 caracteres. Rode de novo.")
else:
    print("\nCopie a linha abaixo para o seu .env:\n")
    print(f"ADMIN_SENHA_HASH='{generate_password_hash(senha)}'")

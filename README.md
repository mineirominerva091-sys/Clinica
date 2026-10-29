# Chama Clínica — aplicação web para TV

Esta versão substitui o Streamlit por uma aplicação web tradicional:

- **Backend:** Flask + SQLAlchemy.
- **Frontend:** HTML, CSS e JavaScript sem framework pesado.
- **Banco:** PostgreSQL compartilhado.
- **Atualização:** polling HTTP a cada 2 segundos, sem WebSocket obrigatório.
- **Deploy recomendado:** Render para o backend + Supabase PostgreSQL.
- **TV:** abrir somente a rota `/tv` no navegador do Fire TV Stick, Android TV Box, mini PC ou navegador moderno.

## Por que Supabase como padrão

Para este sistema, o Supabase é a escolha inicial porque entrega PostgreSQL gerenciado, painel SQL, credenciais de conexão centralizadas e opções de pooler/IPv4 úteis quando o backend está em um provedor externo. O código não depende de recursos proprietários do Supabase: qualquer PostgreSQL compatível funciona. Neon é uma alternativa válida, especialmente se você já usa Neon ou prefere branching de banco; nesse caso, basta trocar `DATABASE_URL`.

Para uso diário em um serviço médico, avalie o plano e a política de pausa/limites do provedor escolhido. A aplicação precisa de um banco persistente, não de SQLite local.

## Funcionalidades

- Login do painel da médica por senha.
- Adicionar paciente à fila.
- Chamar o próximo ou um paciente específico.
- Finalizar, rechamar e cancelar com validação de estado.
- Uma única chamada ativa protegida por índice único no banco.
- Tela da TV sem menus, com paciente, matrícula, consultório, status, fila e última atualização.
- Atualização da TV e do painel a cada 2 segundos por `fetch` HTTP.
- Som de três bipes e anúncio em português após a ativação manual do áudio.
- Histórico recente.
- Token exclusivo para autorizar a TV.
- Endpoint `/health` para monitoramento do deploy.

## Rodar localmente

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
```

Edite `.env` para desenvolvimento. Para testar sem banco remoto, deixe `DATABASE_URL` como:

```env
DATABASE_URL=sqlite:///clinica_local.db
ADMIN_PASSWORD=admin-local
TV_TOKEN=tv-local-2026
SECRET_KEY=uma-chave-local
```

Execute:

```bash
flask --app wsgi:app run --debug
```

Abra:

```text
Painel: http://127.0.0.1:5000/medica
TV:     http://127.0.0.1:5000/tv?token=tv-local-2026
```

Em produção, não use SQLite e não use senhas de exemplo.

## Criar o banco no Supabase

1. Crie um projeto no Supabase.
2. No painel, abra **Connect** e copie a conexão PostgreSQL adequada para uma aplicação externa.
3. Se o provedor oferecer pooler IPv4/session mode, use essa URL no Render quando a conexão direta não for alcançável.
4. Opcionalmente, abra o **SQL Editor** e execute `schema.sql`.
5. Guarde a URL como secret, nunca dentro do GitHub.

A aplicação também cria as tabelas automaticamente no primeiro start, mas executar `schema.sql` é útil para inspecionar e provisionar o banco explicitamente.

## Deploy no Render

1. Envie este diretório para um repositório privado no GitHub.
2. No Render, crie um **Web Service** ligado ao repositório.
3. Use:

```text
Build Command: pip install -r requirements.txt
Start Command: gunicorn --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT wsgi:app
```

4. Cadastre as variáveis privadas:

```env
DATABASE_URL=postgresql://...
ADMIN_PASSWORD=uma-senha-forte
TV_TOKEN=um-token-longo-e-aleatorio
SECRET_KEY=uma-chave-longa-e-aleatoria
FLASK_ENV=production
```

5. Aguarde o deploy e teste `/health`. O Render fornece uma URL HTTPS pública. Opcionalmente, adicione um domínio próprio; o Render gerencia certificado TLS e redirecionamento para HTTPS.

O arquivo `render.yaml` já contém a configuração básica para Blueprint deploy.

## Abrir na TV ou Fire TV Stick

Use a URL pública criada pelo Render:

```text
https://seu-servico.onrender.com/tv?token=SEU_TV_TOKEN
```

No Fire TV Stick:

1. Conecte o Fire Stick ao HDMI da TV.
2. Conecte-o ao Wi-Fi ou hotspot do celular.
3. Abra o Silk Browser.
4. Digite a URL completa da TV, incluindo `?token=...`.
5. Clique uma vez em **Ativar som**.
6. Clique em **Tela cheia** quando o navegador permitir.
7. Salve a URL nos favoritos.

A página da TV não usa Streamlit nem depende de F5. Ela faz uma requisição HTTP a cada 2 segundos. Se o navegador perder a conexão, a própria tela mostra o erro e continua tentando na próxima rodada.

Para preservar a autorização da TV, o token vira um cookie seguro após o primeiro acesso. Se a TV for resetada, abra novamente a URL completa com o token.

## Testes

Instale as dependências e execute:

```bash
pytest -q
```

## Segurança e dados pessoais

O sistema trata nome e matrícula, que podem ser dados pessoais. Antes de uso real, configure HTTPS, senhas fortes, acesso restrito ao painel, backups, retenção mínima e controles de acesso compatíveis com as políticas da organização. Não coloque `DATABASE_URL`, `ADMIN_PASSWORD`, `TV_TOKEN` ou `SECRET_KEY` no GitHub.

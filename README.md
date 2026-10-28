# Chama Clínica — protótipo Streamlit

Sistema básico para testar chamada de pacientes em clínica/serviço médico.

## Funcionalidades
- Painel da médica: adicionar paciente por nome e matrícula, chamar próximo, chamar pessoa específica e finalizar atendimento.
- Tela da recepção/TV: exibe o nome, matrícula e consultório do paciente chamado e atualiza automaticamente a cada 2,5 segundos.
- Notificação sonora com três bipes e tentativa de leitura em voz alta em português (depende das permissões e políticas de autoplay do navegador).
- Histórico recente e opção de limpar dados de demonstração.
- Banco SQLite local para testes em uma única instância do app.

## Executar localmente (Windows)
1. Instale Python 3.10 ou superior.
2. Extraia o ZIP e abra o terminal dentro da pasta.
3. Crie ambiente virtual e instale as dependências:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

O navegador abrirá o sistema. Use o menu lateral para alternar entre **Painel da médica** e **Tela da recepção / TV**.

## Publicar no Streamlit Community Cloud
1. Envie `app.py`, `requirements.txt` e `README.md` para um repositório GitHub.
2. No Streamlit Community Cloud, crie um app selecionando o repositório e o arquivo `app.py`.
3. Publique e teste o link.

### Importante sobre dados
O SQLite local é adequado para demonstração local, mas o armazenamento do Streamlit Cloud pode não ser persistente entre reinicializações/redeploys. Para uso com duas telas em produção, troque SQLite por um banco compartilhado (por exemplo, Supabase/Postgres) e implemente autenticação e controle de acesso. Não use dados reais de pacientes neste protótipo.

## E Vercel?
Streamlit não é executado nativamente na Vercel. Para publicar na Vercel, o caminho recomendado é reconstruir a interface como Next.js e usar Supabase/Postgres para sincronizar o painel da médica e a TV em tempo real. Este ZIP prioriza o teste rápido via Streamlit.

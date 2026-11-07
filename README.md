# SOUZA LIVE: Spike de conexão TikTok LIVE

Ferramenta **descartável** para responder uma pergunta: dá para receber presentes reais de uma live, com usuário, quantidade e sequência, usando conexão direta e gratuita?

Ela **só lê**. Não envia mensagens, não usa session ID, não guarda senha. Não faz parte do SOUZA LIVE final e não tem relação com o SOUZA LIVE RUN.

> **Aviso honesto:** eu escrevi este código sem acesso à internet e sem a biblioteca instalada. Os testes unitários (T-U) provam só a lógica de consolidação. **Nada aqui prova que a conexão funciona.** Quem prova é o seu teste em live real. Erros são esperados e úteis: envie-os.

---

## 1. Instalar o que falta (Windows 10/11)

### 1.1 Python

1. Abra o PowerShell (menu Iniciar, digite `PowerShell`).
2. Rode: `python --version`
   - Se mostrar `Python 3.10` ou superior, pule para 1.2.
   - Se abrir a Microsoft Store ou der erro, rode `py --version`. Se funcionar, use `py` no lugar de `python` em todos os comandos abaixo.
   - Se nenhum funcionar: baixe o Python 3.12 em https://www.python.org/downloads/ . **Na primeira tela do instalador, marque "Add python.exe to PATH"**. Feche e reabra o PowerShell e repita `python --version`.

### 1.2 Preparar a pasta

1. Copie a pasta `souza-live-spike` para um local simples, por exemplo `C:\souza-live-spike`.
2. No PowerShell:

```powershell
cd C:\souza-live-spike
```

### 1.3 Ambiente virtual e biblioteca

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Se aparecer erro de "execução de scripts desabilitada", rode **uma vez**:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Confirme com `S` e repita o `Activate.ps1`. O prompt deve começar com `(.venv)`.

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Se o `pip install` falhar, copie o erro inteiro e me envie.

---

## 2. Testes

### T-U: testes unitários (lógica de sequências)

```powershell
python -m unittest -v
```

Esperado: `Ran 9 tests ... OK`.

### T0: verificação do ambiente

```powershell
python check_env.py
```

Mostra versão do Python, se a biblioteca está instalada e se o site do TikTok responde. Copie a saída.

### T1: linha de base (padrão da biblioteca, sem chave)

Precisa de alguém **em live agora**. Use a sua própria live ou uma live pública de movimento alto (apenas para ver o formato dos eventos).

```powershell
python tiktok_probe.py NOME_DO_USUARIO --duration 300 --label T1 --anonymize
```

- `NOME_DO_USUARIO` é o @ sem o arroba.
- `--duration 300` encerra após 5 minutos. Sem ele, use Ctrl+C.
- `--anonymize` mascara IDs, @ e apelidos nos arquivos (recomendado antes de me enviar).

Ao fim, a pasta `logs\` terá:

- `T1_AAAAMMDD_HHMMSS.jsonl`: todos os eventos;
- `T1_..._relatorio.md`: resumo.

### T2: servidor de assinatura próprio (**não execute ainda**)

Só depois de revisarmos juntos o código de um candidato (ver `docs\SIGN_SERVER_CANDIDATES.md`). Então:

```powershell
python check_env.py --sign-url http://127.0.0.1:8080
python tiktok_probe.py NOME_DO_USUARIO --duration 300 --label T2 --sign-url http://127.0.0.1:8080 --anonymize
```

### T3: presentes, usuário, quantidade e sequência (o teste que mais importa)

Objetivo: comparar o que **você realmente enviou** com o que o programa consolidou.

1. Inicie uma live na sua conta (conta A).
2. Rode: `python tiktok_probe.py SUA_CONTA --duration 600 --label T3 --anonymize`
3. Com **outra conta** (B), entre na live e envie presentes. Anote cada envio na tabela abaixo.
4. Inclua pelo menos: um presente de clique único; um presente de sequência com cliques rápidos (ex.: 5 vezes seguidas); duas contas enviando o mesmo presente ao mesmo tempo, se possível; uma pausa longa no meio de uma sequência.
5. Ao terminar, aperte Ctrl+C na janela do programa. Ele gera o relatório.

Tabela de verdade (preencha enquanto testa):

| Hora aprox. | Conta | Presente | Cliques / quantidade enviada | Observação |
|---|---|---|---|---|
| | | | | |

**Custo:** presentes usam moedas do TikTok (dinheiro de verdade). Use presentes de valor mínimo e poucas repetições. Se não quiser gastar, o T1 em uma live pública já mostra o formato dos eventos, mas **não** prova a contagem exata.

---

## 3. O que me enviar

Cole na conversa (ou envie os arquivos):

1. Saída completa do `check_env.py`.
2. O arquivo `*_relatorio.md` de cada teste.
3. O `.jsonl` (se for grande, envie as primeiras 200 linhas mais as linhas com `"kind": "gift_event"` e `"gift_final"`).
4. Sua tabela de verdade do T3.
5. Qualquer erro de tela, completo.

Use `--anonymize`: ele mascara IDs, @, apelidos, o room_id e o seu @ dentro de mensagens de erro, e não grava texto de comentários. Ele **não** esconde horários, nomes e valores dos presentes; quem conhece a live pode correlacionar um presente específico a um espectador. Não publique os arquivos. **Nunca envie** cookies, session ID, senhas ou chaves de API.

---

## 4. Problemas comuns

| Sintoma | Provável causa | O que fazer |
|---|---|---|
| `python` abre a Microsoft Store | Python não instalado/PATH | Seção 1.1 |
| `Activate.ps1 ... desabilitada` | Política de execução | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `No module named TikTokLive` | Ambiente virtual não ativado ou pip falhou | Ative `.venv` e rode `pip install -r requirements.txt` |
| Erro mencionando "offline" | O usuário não está em live | Confirme no app/site |
| Erro mencionando "sign", "429" ou "rate" | Limite ou queda do servidor de assinatura | Anote horário e mensagem; envie. É o dado principal do T1 |
| Conecta mas não chegam presentes | Live sem presentes, ou mudança de protocolo | Compare com o app; envie o log |
| `[ERRO HANDLER]` | Campo diferente do esperado na biblioteca | Envie; o log `schema` mostra os campos reais |

---

## 5. Limitações conhecidas deste spike

- Não testa reconexão após queda (fica para a próxima etapa).
- Só mede a biblioteca Python. Se a T2 exigir a biblioteca Node, farei uma variante.
- Os nomes dos campos (`repeat_count`, `repeat_end`, `streakable`) vêm da documentação da biblioteca; o programa registra o esquema real no log para corrigirmos.
- Esta ferramenta usa um serviço não oficial e pode violar os termos do TikTok. Use por sua conta e risco, de preferência na sua própria live.

# Scope Guard Template — Service Isolation

Copy this template when creating a new service that runs as a Telegram topic agent.
Three isolation layers must all be present.

---

## Layer 1: CLAUDE.md — Hard Forbidden List

Add this section to the service's `CLAUDE.md`. Replace `<service-name>` throughout.

```markdown
## ЗАПРЕЩЁННЫЕ ДЕЙСТВИЯ (жёсткий контроль)

Следующие действия ЗАПРЕЩЕНЫ независимо от задачи:

### Запрещённые bash-команды
- `find /` — поиск по всей файловой системе
- `find ..` — выход в родительскую директорию
- `grep -r ... /Users` — поиск по путям вне <service-name>/
- `grep -r ... ..` — grep в родительской директории
- `cat`, `ls`, `read` любых файлов вне `<service-name>/`
- `cd ..`, `cd /` — смена директории за пределы сервиса

### Запрещённый доступ к файлам
- `topic_config.json` — приватная конфигурация workspace
- Любые файлы других сервисов workspace

### Реакция на нехватку контекста
Если чего-то не хватает — СТОП + сообщение пользователю.
Никогда не ищи недостающее самостоятельно.
```

---

## Layer 2: System Prompt (mode.md) — Scope Guard Header

Add this block at the **very top** of the mode's `.md` prompt file, before any other content.

```markdown
## SCOPE GUARD — прочти первым

Твоя единственная задача: <one-line description of what this service does>.

**Запрещено:**
- Запускать `find`, `grep -r`, `ls` за пределами текущей директории
- Читать или писать файлы вне `<service-name>/`
- Искать код, конфигурацию или данные в других сервисах
- Пытаться самостоятельно найти недостающие параметры

**Если чего-то не хватает — стоп:**

| Что отсутствует | Действие |
|----------------|----------|
| `<required_param>` в `<telegram-context>` | Отправить: `❌ <Param> не настроен...` |
| `<ENV_VAR>` в `.env` | Отправить: `❌ Токен не настроен...` |
| Что-либо ещё непонятно | Отправить сообщение с описанием проблемы |

Никогда не ищи недостающее — всегда репортируй.
```

---

## Layer 3: Tool Allowlist (cc_modes.py)

In `telegram-ai-agent/src/telegram_bot/core/services/cc_modes.py`, define the tool set
for your mode using only what the pipeline actually needs. Remove `Grep`, `Glob`, `Agent`,
`Edit` — these enable arbitrary codebase search.

```python
# Minimal example: write a file, run a script, read output
MY_SERVICE_MODE_TOOLS = f"{_BOT_MCP_TOOLS},Bash,Write,Read"
```

Tool allowlist reference:

| Tool   | Allow? | Reason |
|--------|--------|--------|
| `Bash` | Yes    | Run the service's own CLI scripts |
| `Write`| Yes    | Create input files for CLI (e.g. task.json) |
| `Read` | Yes    | Read CLI output files |
| `Grep` | No     | Enables searching outside service scope |
| `Glob` | No     | Enables file discovery outside service scope |
| `Agent`| No     | Spawns sub-agents with unrestricted tool access |
| `Edit` | No     | Not needed for script-based pipelines |

---

## Checklist

Before shipping a new topic-based service, verify:

- [ ] `CLAUDE.md` has `## ЗАПРЕЩЁННЫЕ ДЕЙСТВИЯ` section with forbidden bash commands
- [ ] System prompt (`<mode>.md`) starts with `## SCOPE GUARD — прочти первым`
- [ ] Tool allowlist in `cc_modes.py` omits `Grep`, `Glob`, `Agent`, `Edit`
- [ ] `topic_config.json` entry has `cwd` pointing to the service directory
- [ ] Service has its own `.env.example` documenting required env vars
- [ ] All required params are injected via `<telegram-context>` by `_build_tg_context`
- [ ] Mode fails fast with a clear message when required context is missing

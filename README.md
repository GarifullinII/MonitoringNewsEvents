# Monitoring News Events

Python MVP для AI-мониторинга инфоповодов по GEO с автоматической генерацией:

- сырых инфоповодов
- маркетинговых углов
- заголовков
- shortlist рекомендаций
- риск-анализа
- Markdown и JSON выпуска

Репозиторий собран под ТЗ "Мониторинг инфоповодов" и рассчитан на запуск 2 раза в неделю по приоритетным GEO.

## Что уже реализовано

- сбор новостей из `RSS`, `Google News RSS` и локальных RSS-файлов для офлайн-прогонов
- эвристическая классификация по категориям: экономика, политика, соцсети, селеба, скандал, банки-налоги, страхи
- оценка эмоционального триггера: деньги, кризис, возможность, страх, доверие
- генерация 5-10+ инфоповодов, 20-30 идей и 30-50 заголовков в рамках одного выпуска
- shortlist топ-идей с обоснованием
- блок рисков и отдельный блок срочности
- хранение артефактов в `outputs/` и нормализованных сущностей в `data/knowledge_base/*.jsonl`
- публикация структуры выпуска в Airtable
- поддержка сценария `Airtable template -> Document URL -> Telegram`
- optional LLM enrichment через OpenAI Responses API
- optional уведомления в Slack и Telegram

## Архитектура

Пайплайн:

1. Источники новостей по GEO
2. Нормализация и дедупликация статей
3. Сырые инфоповоды
4. Углы и идеи
5. Заголовки
6. Топ-рекомендации
7. Риски и срочность
8. Генерация выпуска в Markdown и JSON
9. Публикация в Airtable и ожидание `Document URL` из шаблона/automation
10. Отправка ссылки в Telegram
11. Сохранение в локальную базу знаний

Ключевые файлы:

- [main.py](/Users/ildargarifullin/Desktop/Development/python/MonitoringNewsEvents/main.py)
- [src/monitoring_news_events/airtable.py](/Users/ildargarifullin/Desktop/Development/python/MonitoringNewsEvents/src/monitoring_news_events/airtable.py)
- [src/monitoring_news_events/pipeline.py](/Users/ildargarifullin/Desktop/Development/python/MonitoringNewsEvents/src/monitoring_news_events/pipeline.py)
- [src/monitoring_news_events/openai_client.py](/Users/ildargarifullin/Desktop/Development/python/MonitoringNewsEvents/src/monitoring_news_events/openai_client.py)
- [src/monitoring_news_events/reporting.py](/Users/ildargarifullin/Desktop/Development/python/MonitoringNewsEvents/src/monitoring_news_events/reporting.py)
- [configs/project.example.toml](/Users/ildargarifullin/Desktop/Development/python/MonitoringNewsEvents/configs/project.example.toml)

## Быстрый старт

Без установки:

```bash
python3 main.py list-geos
python3 main.py run --geo latam-demo --disable-llm
```

Через editable install:

```bash
python3 -m pip install -e .
news-monitor list-geos
news-monitor run --geo latam-demo --disable-llm
```

## Какие ключи и доступы нужны

Проект можно запускать в трех режимах.

### 1. Локальный тестовый запуск без внешних интеграций

Ничего из ключей не требуется, если вы:

- запускаете проект на `local_rss`
- используете heuristic-only режим
- не публикуете выпуск в Airtable
- не отправляете ссылку в Telegram

Команда:

```bash
python3 main.py run --geo latam-demo --disable-llm
```

### 2. Боевой запуск через Airtable и Telegram

Для основного сценария из ТЗ нужны:

- `AIRTABLE_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Также нужны доступы:

- доступ на запись в Airtable base, указанный в `base_id`
- доступ на создание и чтение записей в таблицах `Reports`, `Inforeasons`, `Angles`, `Headlines`, `Recommendations`, `Risks`
- если Airtable automation или шаблон создает итоговый документ, у automation должен быть доступ записывать ссылку в поле `Document URL`
- Telegram-бот должен быть добавлен в нужный чат, группу или канал
- бот должен иметь право отправлять сообщения в этот чат

### 3. Улучшенный запуск с LLM enrichment

Если хотите, чтобы углы, заголовки и рекомендации дополнительно усиливались через OpenAI API, нужен:

- `OPENAI_API_KEY`

Также нужно:

- включить `[llm].enabled = true` или не отключать LLM флагом `--disable-llm`
- разрешить исходящие запросы к OpenAI API

### Что обязательно, а что опционально

Обязательно для полного прод-сценария:

- `AIRTABLE_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `airtable.base_id` в конфиге

Опционально:

- `OPENAI_API_KEY` для LLM enrichment
- `SLACK_WEBHOOK_URL`, если хотите дублировать уведомление в Slack

Не нужны отдельные API-ключи для:

- `local_rss`
- обычных `rss`
- `Google News RSS`

### Какие права должны быть у Airtable

Минимально проекту нужен Airtable token, который позволяет:

- читать и создавать записи в нужной base
- создавать связанные записи между таблицами
- читать обратно `Reports` record, чтобы дождаться поля `Document URL`

Практически это означает, что токен должен иметь доступ к той base, где лежат рабочие таблицы проекта.

### Какие права должны быть у Telegram

Минимально нужно:

- создать Telegram bot через BotFather
- получить `TELEGRAM_BOT_TOKEN`
- добавить бота в целевой чат или канал
- получить `TELEGRAM_CHAT_ID`
- убедиться, что боту разрешено писать в этот чат

### Рекомендуемый `.env` набор

```bash
export AIRTABLE_TOKEN=...
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
export OPENAI_API_KEY=...
export SLACK_WEBHOOK_URL=...
```

### Минимум для запуска именно вашего сценария

Если запускать проект так, как он задуман в ТЗ, минимальный набор такой:

- `AIRTABLE_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- Airtable base с настроенными таблицами и полем `Document URL`

## Конфигурация

Основной конфиг лежит в TOML. Пример:

```toml
[project]
report_dir = "outputs"
data_dir = "data"
coverage_days = 7
signal_limit = 12
idea_limit = 24
headlines_per_idea = 3

[llm]
enabled = false
provider = "openai_responses"
model = "gpt-4.1-mini"
api_key_env = "OPENAI_API_KEY"

[airtable]
enabled = true
api_token_env = "AIRTABLE_TOKEN"
base_id = "appXXXXXXXXXXXXXX"
report_link_field = "Document URL"

  [airtable.tables]
  reports = "Reports"
  raw_signals = "Inforeasons"
  angles = "Angles"
  headlines = "Headlines"
  recommendations = "Recommendations"
  risks = "Risks"

[[geo]]
id = "latam-demo"
name = "Chile"
owner = "LATAM TL"
offer_name = "Финансовый оффер"
offer_description = "Нативные углы вокруг сохранения бюджета и дополнительного дохода."

  [[geo.source]]
  kind = "google_news_rss"
  name = "Google News"
  source_type = "топовое СМИ"
  category = "экономика"
  query = "Chile inflation taxes salaries banks"
```

Поддержанные `kind`:

- `google_news_rss`
- `rss`
- `local_rss`

## LLM enrichment

Если нужен не только heuristic режим, включите:

```bash
export OPENAI_API_KEY=...
python3 main.py run --geo latam-demo
```

Код использует OpenAI Responses API со structured JSON output. Если ключа нет, пайплайн автоматически остается в heuristic-only режиме.

## Выходные артефакты

- `outputs/<geo_id>/<timestamp>.md` — человекочитаемый выпуск
- `outputs/<geo_id>/<timestamp>.json` — полная структура отчета
- `data/knowledge_base/inforeasons.jsonl`
- `data/knowledge_base/angles.jsonl`
- `data/knowledge_base/headlines.jsonl`
- `data/knowledge_base/reports.jsonl`

Если Airtable включен, дополнительно создается `report` record и связанные записи в таблицах:

- `Reports`
- `Inforeasons`
- `Angles`
- `Headlines`
- `Recommendations`
- `Risks`

В таблице `Reports` код ожидает, что ваш Airtable-шаблон или automation заполнит поле `Document URL`. Именно эта ссылка потом уходит в Telegram.

## Обратная связь по прошлым выпускам

Для каждого GEO можно завести файл:

- `data/feedback/<geo_id>.json`

Пример структуры:

```json
{
  "entries": [
    {
      "report_date": "2026-05-20",
      "winners": ["банк и комиссии", "рост цен на продукты"],
      "losers": ["слишком общий политический угол"],
      "lessons": ["лучше заходят конкретные бытовые деньги", "новость должна быть свежей до 72 часов"]
    }
  ]
}
```

## Airtable и Telegram

Минимальная схема для `Reports`:

- `Name`
- `Report ID`
- `GEO ID`
- `GEO Name`
- `Generated At`
- `Coverage Period`
- `Owner`
- `Offer Name`
- `Previous Report URL`
- `Feedback Summary`
- `Urgency Hot`
- `Urgency Later`
- `Notes`
- `Shortlist Summary`
- `Report Markdown`
- `Report JSON`
- `Local Markdown Path`
- `Local JSON Path`
- `Raw Signal Count`
- `Angle Count`
- `Headline Count`
- `LLM Used`
- `Document URL`

Для linked records код использует поля:

- в `Inforeasons`: `Report`
- в `Angles`: `Report`, `Raw Signal`
- в `Headlines`: `Report`, `Angle`
- в `Recommendations`: `Report`, `Angle`, `Raw Signal`
- в `Risks`: `Report`, `Raw Signal`

Рекомендуемый сценарий:

1. Пайплайн создает `Reports` record и все дочерние записи.
2. Airtable automation или template engine берет `Report Markdown` или связанные записи и собирает итоговый документ.
3. Automation записывает публичную ссылку в поле `Document URL`.
4. Код ждет это поле и отправляет ссылку в Telegram.

При наличии env-переменных доступны уведомления:

- `AIRTABLE_TOKEN`
- `SLACK_WEBHOOK_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Запуск:

```bash
python3 main.py run --geo latam-demo --notify
```

Если `Document URL` еще не появился, код попробует подождать несколько polling-циклов. Если поле так и не заполнено, в Telegram уйдет fallback-ссылка на Airtable record, если задан `reports` table id или `report_record_url_template`.

## Ограничения и следующая итерация

- сейчас шаблонный документ предполагается на стороне Airtable automation/interface
- field mapping в Airtable пока фиксированный и описан в README
- для production удобно будет вынести field mapping в конфиг и добавить отдельный adapter под Google Docs
- качество категорий и углов в heuristic режиме ниже, чем в LLM режиме
- перед продом нужен редакторский review, особенно для политических, scandal и celebrity тем

## Принципы безопасности

Система специально не генерирует гарантии дохода, не маскирует рекламу под редакционную статью и не должна использоваться для клеветы, фрода или обхода правил платформ.

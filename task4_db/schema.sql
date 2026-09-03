-- Задание 4. Схема БД «Тендерная площадка» (PostgreSQL 14+).
--
-- Роли сущностей:
--   companies   — юрлица: и заказчики тендеров, и участники торгов. Разделять их
--                 на две таблицы нельзя: одна и та же компания в одном тендере
--                 заказчик, в другом — участник.
--   contractors — исполнитель как роль компании по конкретному договору
--                 (победитель лота), с датами и статусом исполнения.
--   tenders     — закупка целиком; lots — то, на что реально подают ставки;
--                 bids — ставка компании по лоту.
--
-- Деньги — numeric(16,2): double portable, но не считает деньги.
-- Все суммы в одной валюте лота, валюта хранится рядом с суммой.

BEGIN;

CREATE TABLE companies (
    id              bigserial PRIMARY KEY,
    inn             varchar(12) NOT NULL,
    kpp             varchar(9),
    name            text        NOT NULL,
    region_code     smallint,
    is_customer     boolean     NOT NULL DEFAULT false,
    is_supplier     boolean     NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT companies_inn_uniq UNIQUE (inn),
    CONSTRAINT companies_inn_digits CHECK (inn ~ '^[0-9]{10}$' OR inn ~ '^[0-9]{12}$')
);

CREATE TABLE tenders (
    id              bigserial PRIMARY KEY,
    external_id     text        NOT NULL,           -- номер извещения на площадке
    customer_id     bigint      NOT NULL REFERENCES companies (id) ON DELETE RESTRICT,
    title           text        NOT NULL,
    law             varchar(8)  NOT NULL,           -- 44-ФЗ / 223-ФЗ
    procedure_type  varchar(32) NOT NULL,           -- аукцион, конкурс, запрос котировок
    status          varchar(16) NOT NULL DEFAULT 'published',
    published_at    timestamptz NOT NULL,
    bids_close_at   timestamptz NOT NULL,
    total_amount    numeric(16, 2),                 -- НМЦ всего тендера, справочно
    currency        char(3)     NOT NULL DEFAULT 'RUB',
    CONSTRAINT tenders_external_uniq UNIQUE (external_id),
    CONSTRAINT tenders_status_chk CHECK (
        status IN ('draft', 'published', 'bidding', 'evaluation', 'awarded', 'cancelled')
    ),
    CONSTRAINT tenders_window_chk CHECK (bids_close_at > published_at),
    CONSTRAINT tenders_amount_chk CHECK (total_amount IS NULL OR total_amount >= 0)
);

CREATE TABLE lots (
    id              bigserial PRIMARY KEY,
    tender_id       bigint      NOT NULL REFERENCES tenders (id) ON DELETE CASCADE,
    lot_number      integer     NOT NULL,
    title           text        NOT NULL,
    okpd2           varchar(20),
    start_price     numeric(16, 2) NOT NULL,        -- НМЦ лота
    currency        char(3)     NOT NULL DEFAULT 'RUB',
    delivery_region smallint,
    CONSTRAINT lots_number_uniq UNIQUE (tender_id, lot_number),
    CONSTRAINT lots_price_chk CHECK (start_price > 0)
);

CREATE TABLE bids (
    id              bigserial PRIMARY KEY,
    lot_id          bigint      NOT NULL REFERENCES lots (id) ON DELETE CASCADE,
    company_id      bigint      NOT NULL REFERENCES companies (id) ON DELETE RESTRICT,
    amount          numeric(16, 2) NOT NULL,
    submitted_at    timestamptz NOT NULL DEFAULT now(),
    status          varchar(16) NOT NULL DEFAULT 'submitted',
    is_winner       boolean     NOT NULL DEFAULT false,
    CONSTRAINT bids_amount_chk CHECK (amount > 0),
    CONSTRAINT bids_status_chk CHECK (
        status IN ('submitted', 'withdrawn', 'rejected', 'accepted')
    )
);

-- Одна действующая ставка компании на лот. Отозванные не мешают подать новую,
-- поэтому уникальность частичная, а не по всей таблице.
CREATE UNIQUE INDEX bids_one_active_per_company ON bids (lot_id, company_id)
    WHERE status <> 'withdrawn';

-- Победитель у лота ровно один. Частичный уникальный индекс — это ограничение
-- целостности, а не оптимизация: без него две строки с is_winner = true
-- проходят любую проверку в приложении.
CREATE UNIQUE INDEX bids_single_winner_per_lot ON bids (lot_id) WHERE is_winner;

CREATE TABLE contractors (
    id              bigserial PRIMARY KEY,
    lot_id          bigint      NOT NULL REFERENCES lots (id) ON DELETE RESTRICT,
    company_id      bigint      NOT NULL REFERENCES companies (id) ON DELETE RESTRICT,
    bid_id          bigint      NOT NULL REFERENCES bids (id) ON DELETE RESTRICT,
    contract_number text        NOT NULL,
    contract_amount numeric(16, 2) NOT NULL,
    signed_at       date        NOT NULL,
    deadline_at     date,
    status          varchar(16) NOT NULL DEFAULT 'active',
    CONSTRAINT contractors_lot_uniq UNIQUE (lot_id),
    CONSTRAINT contractors_number_uniq UNIQUE (contract_number),
    CONSTRAINT contractors_amount_chk CHECK (contract_amount > 0),
    CONSTRAINT contractors_status_chk CHECK (
        status IN ('active', 'completed', 'terminated', 'disputed')
    ),
    CONSTRAINT contractors_deadline_chk CHECK (deadline_at IS NULL OR deadline_at >= signed_at)
);

-- Индексы под фактические запросы мониторинга, а не «на каждый столбец».
CREATE INDEX tenders_published_at_idx   ON tenders (published_at DESC);
CREATE INDEX tenders_customer_idx       ON tenders (customer_id, published_at DESC);
CREATE INDEX tenders_open_idx           ON tenders (bids_close_at) WHERE status IN ('published', 'bidding');
CREATE INDEX lots_tender_idx            ON lots (tender_id);
CREATE INDEX lots_okpd2_idx             ON lots (okpd2) WHERE okpd2 IS NOT NULL;
CREATE INDEX bids_lot_amount_idx        ON bids (lot_id, amount);
CREATE INDEX bids_company_time_idx      ON bids (company_id, submitted_at DESC);
CREATE INDEX contractors_company_idx    ON contractors (company_id, signed_at DESC);
CREATE INDEX contractors_signed_at_idx  ON contractors (signed_at DESC);

COMMIT;

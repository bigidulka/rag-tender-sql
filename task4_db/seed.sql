-- Небольшой набор данных, чтобы запросы из queries.sql можно было запустить
-- и увидеть непустой результат. Даты считаются от текущей: договоры кладём в
-- прошлый месяц и прошлый квартал, чтобы попасть в окна обоих запросов.

BEGIN;

INSERT INTO companies (inn, name, region_code, is_customer, is_supplier) VALUES
    ('7701234567', 'ГБУ «Городская инфраструктура»', 77, true,  false),
    ('7802345678', 'ГКУ «Дорожное хозяйство»',       78, true,  false),
    ('7703456789', 'ООО «СтройПодряд»',              77, false, true),
    ('5904567890', 'ООО «ИТ-Интегратор»',            59, false, true),
    ('6605678901', 'АО «Северные сети»',             66, false, true),
    ('7706789012', 'ООО «Проектный офис»',           77, false, true);

INSERT INTO tenders (external_id, customer_id, title, law, procedure_type, status, published_at, bids_close_at, total_amount)
SELECT
    v.external_id,
    c.id,
    v.title,
    v.law,
    v.procedure_type,
    'awarded',
    (date_trunc('month', current_date) - interval '2 months')::timestamptz,
    (date_trunc('month', current_date) - interval '1 month' - interval '2 days')::timestamptz,
    v.total_amount
FROM (VALUES
    ('0173200001225000101', '7701234567', 'Ремонт дворовых территорий',        '44-ФЗ', 'аукцион',           12000000.00),
    ('0173200001225000102', '7701234567', 'Поставка серверного оборудования',  '44-ФЗ', 'аукцион',            8000000.00),
    ('0372200002225000201', '7802345678', 'Содержание дорожной сети',          '44-ФЗ', 'конкурс',           25000000.00)
) AS v (external_id, customer_inn, title, law, procedure_type, total_amount)
JOIN companies AS c ON c.inn = v.customer_inn;

INSERT INTO lots (tender_id, lot_number, title, okpd2, start_price)
SELECT t.id, v.lot_number, v.title, v.okpd2, v.start_price
FROM (VALUES
    ('0173200001225000101', 1, 'Асфальтирование, участок А', '42.11.20', 7000000.00),
    ('0173200001225000101', 2, 'Асфальтирование, участок Б', '42.11.20', 5000000.00),
    ('0173200001225000102', 1, 'Серверы и СХД',              '26.20.13', 8000000.00),
    ('0372200002225000201', 1, 'Зимнее содержание',          '42.11.20', 25000000.00)
) AS v (external_id, lot_number, title, okpd2, start_price)
JOIN tenders AS t ON t.external_id = v.external_id;

INSERT INTO bids (lot_id, company_id, amount, submitted_at, status, is_winner)
SELECT l.id, c.id, v.amount,
       (date_trunc('month', current_date) - interval '1 month' - interval '5 days')::timestamptz,
       v.status, v.is_winner
FROM (VALUES
    ('0173200001225000101', 1, '7703456789', 6300000.00, 'accepted',  true),
    ('0173200001225000101', 1, '7706789012', 6600000.00, 'rejected',  false),
    ('0173200001225000101', 2, '7703456789', 4800000.00, 'accepted',  true),
    ('0173200001225000101', 2, '6605678901', 4950000.00, 'rejected',  false),
    ('0173200001225000102', 1, '5904567890', 6400000.00, 'accepted',  true),
    ('0173200001225000102', 1, '6605678901', 7100000.00, 'rejected',  false),
    ('0173200001225000102', 1, '7706789012', 7500000.00, 'withdrawn', false),
    ('0372200002225000201', 1, '6605678901', 23750000.00, 'accepted', true),
    ('0372200002225000201', 1, '7703456789', 24100000.00, 'rejected', false)
) AS v (external_id, lot_number, company_inn, amount, status, is_winner)
JOIN tenders   AS t ON t.external_id = v.external_id
JOIN lots      AS l ON l.tender_id = t.id AND l.lot_number = v.lot_number
JOIN companies AS c ON c.inn = v.company_inn;

INSERT INTO contractors (lot_id, company_id, bid_id, contract_number, contract_amount, signed_at, deadline_at, status)
SELECT b.lot_id, b.company_id, b.id,
       'CN-' || b.id::text,
       b.amount,
       (date_trunc('month', current_date) - interval '1 month' + interval '3 days')::date,
       (date_trunc('month', current_date) + interval '2 months')::date,
       'active'
FROM bids AS b
WHERE b.is_winner;

COMMIT;

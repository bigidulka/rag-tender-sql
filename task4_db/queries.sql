-- Задание 4, часть 2: два аналитических запроса.

-- ---------------------------------------------------------------------------
-- Запрос 1. Топ-3 компании по сумме выигранных тендеров за последний месяц.
--
-- «Выигранный» считаем по подписанному договору (contractors), а не по флагу
-- is_winner в ставке: между объявлением победителя и договором лот может
-- уйти второму участнику. Окно — календарный предыдущий месяц; date_trunc с
-- интервалом даёт границы без падения индекса, потому что условие остаётся
-- диапазонным по signed_at.
-- ---------------------------------------------------------------------------
SELECT
    c.id                                AS company_id,
    c.inn,
    c.name,
    count(*)                            AS contracts_won,
    sum(ct.contract_amount)             AS total_amount,
    round(avg(ct.contract_amount), 2)   AS avg_amount
FROM contractors AS ct
JOIN companies   AS c ON c.id = ct.company_id
WHERE ct.signed_at >= date_trunc('month', current_date) - interval '1 month'
  AND ct.signed_at <  date_trunc('month', current_date)
  AND ct.status <> 'terminated'
GROUP BY c.id, c.inn, c.name
ORDER BY total_amount DESC, contracts_won DESC
LIMIT 3;

-- ---------------------------------------------------------------------------
-- Запрос 2. Конкуренция и падение цены по лотам, закрытым в текущем квартале:
-- сколько участников торговалось, на сколько процентов победитель опустил НМЦ
-- и как это выглядит в разрезе заказчика.
--
-- Окно — квартал с его начала по сегодня. Для отчёта по завершённому кварталу
-- граница сдвигается на один интервал:
--     signed_at >= date_trunc('quarter', current_date) - interval '3 months'
--     AND signed_at < date_trunc('quarter', current_date)
-- Условие в обоих случаях остаётся диапазонным, поэтому
-- contractors_signed_at_idx работает.
--
-- Оконная функция вместо второго GROUP BY: ранг заказчика по среднему падению
-- цены считается на уже агрегированном наборе, лишнего прохода по bids нет.
-- ---------------------------------------------------------------------------
WITH closed_lots AS (
    SELECT
        l.id                AS lot_id,
        l.tender_id,
        t.customer_id,
        l.start_price,
        ct.contract_amount,
        ct.signed_at
    FROM lots        AS l
    JOIN tenders     AS t  ON t.id = l.tender_id
    JOIN contractors AS ct ON ct.lot_id = l.id
    WHERE ct.signed_at >= date_trunc('quarter', current_date)
      AND ct.signed_at <  date_trunc('quarter', current_date) + interval '3 months'
),
bid_stats AS (
    SELECT
        lot_id,
        count(DISTINCT company_id) AS bidders
    FROM bids
    WHERE status <> 'withdrawn'
      AND lot_id IN (SELECT lot_id FROM closed_lots)
    GROUP BY lot_id
)
SELECT
    cu.name                                                       AS customer,
    count(*)                                                      AS lots_closed,
    round(avg(COALESCE(bs.bidders, 0)), 2)                        AS avg_bidders,
    round(avg(
        100 * (cl.start_price - cl.contract_amount) / cl.start_price
    ), 2)                                                         AS avg_discount_pct,
    rank() OVER (
        ORDER BY avg(100 * (cl.start_price - cl.contract_amount) / cl.start_price) DESC
    )                                                             AS discount_rank
FROM closed_lots AS cl
JOIN companies   AS cu ON cu.id = cl.customer_id
LEFT JOIN bid_stats AS bs ON bs.lot_id = cl.lot_id
GROUP BY cu.id, cu.name
HAVING count(*) >= 1
ORDER BY avg_discount_pct DESC;

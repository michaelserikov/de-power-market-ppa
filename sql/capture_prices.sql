-- Capture prices by technology and period, from the hourly table.
--   baseload price = mean of hourly prices
--   capture price  = generation-weighted mean price: sum(price * gen) / sum(gen)
--   capture rate   = capture price / baseload price
-- {period} is replaced by the caller with `year` or `year, month`.

WITH gen AS (
    UNPIVOT hourly
    ON wind_onshore, wind_offshore, solar
    INTO NAME tech VALUE mwh
),
base AS (
    SELECT {period},
           avg(price)                                   AS baseload_price,
           avg(CASE WHEN price < 0 THEN 1.0 ELSE 0 END) AS share_negative_hours
    FROM hourly
    GROUP BY {period}
)
SELECT {period},
       g.tech,
       sum(g.mwh) / 1e6                                              AS generation_twh,
       sum(g.price * g.mwh) / sum(g.mwh)                             AS capture_price,
       b.baseload_price,
       (sum(g.price * g.mwh) / sum(g.mwh)) / b.baseload_price        AS capture_rate,
       sum(CASE WHEN g.price < 0 THEN g.mwh ELSE 0 END) / sum(g.mwh) AS share_gen_negative_price,
       -- capture price if the plant does not produce in negative-price hours
       sum(CASE WHEN g.price >= 0 THEN g.price * g.mwh ELSE 0 END)
         / sum(CASE WHEN g.price >= 0 THEN g.mwh ELSE 0 END)         AS capture_price_curtailed,
       b.share_negative_hours
FROM gen AS g
JOIN base AS b USING ({period})
GROUP BY {period}, g.tech, b.baseload_price, b.share_negative_hours
ORDER BY {period}, g.tech;

# Elregning

Home Assistant-integration (Claude AI, 2026-11-01): skriv elregningerne ind og hold dem op mod det, HA selv har målt.

- Elmåler og omkostning hentes fra energi-dashboardets net-forbrug (kan ændres under Konfigurer).
- Hver regning sammenlignes med egen måling for samme dage: kWh og kr (forbrug × Strømligning-pris).
- Forholdet regning ÷ egen beregning på de seneste 3 hele regninger retter prognosen for denne måned.
- Prognose = målt indtil nu + resten af måneden med de seneste 14 dages gennemsnit × forholdet.

Tjenester: `elregning.add_bill`, `elregning.update_bill`, `elregning.delete_bill`.
Sensorer: Prognose denne måned, Målt denne måned, Seneste regning (alle regninger i attributten `regninger`), Afvigelse seneste regning.

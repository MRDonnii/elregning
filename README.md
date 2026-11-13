# Elregning

Home Assistant-integration: skriv elregningerne ind og hold dem op mod det, Home Assistant selv har målt – og se, hvad
denne måneds regning forventes at lande på.

*Home Assistant integration: enter your electricity bills, compare them with Home Assistant's own measurement for the
same days and get a forecast for this month's bill.*

## Sådan virker den

- Elmåler (kWh) og omkostning (kr) hentes fra energi-dashboardets net-forbrug. Omkostningen er den sensor, energi-
  dashboardet selv laver ud fra forbrug × elpris (fx Strømligning). Begge kan ændres under **Konfigurer**.
- Hver regning sammenlignes med HA's egen måling for præcis de samme dage: kWh og kroner, afvigelse i kr og %.
- Forholdet *regning ÷ egen beregning* over de seneste 3 hele regninger bruges til at rette prognosen, så faste gebyrer,
  abonnementer og små prisforskelle kommer med.
- **Prognose** = målt indtil nu i måneden + resten af måneden med de seneste 14 dages gennemsnit, × forholdet.

## Installation

HACS → Integrationer → ⋮ → Brugerdefinerede repositories → `https://github.com/MRDonnii/elregning` (Integration).
Installér **Elregning**, genstart Home Assistant og tilføj integrationen under Indstillinger → Enheder og tjenester.

## Tjenester

| Tjeneste | Felter |
|---|---|
| `elregning.add_bill` | `start_date`, `end_date`, `amount` (kr inkl. moms), valgfrit `kwh`, `m3`, `utility` (`el`/`gas`, standard `el`), `supplier`, `note` – svarer med `id` |
| `elregning.update_bill` | `id` + de felter, der skal ændres |
| `elregning.delete_bill` | `id` |

## Sensorer

- **Prognose denne måned** (kr) – attributter: egen beregning, forventet kWh, forhold, målt indtil nu, dagligt
  gennemsnit, målt pr. måned (`maaneder`).
- **Målt denne måned** (kr, attribut `kwh`).
- **Seneste regning** (kr) – elregningerne med sammenligning i attributten `regninger`, gasregningerne i
  `gasregninger` og alt lagt sammen pr. år og forsyning i `aar`. Gas holdes ikke op mod elmåleren og påvirker ikke
  prognosen.
- **Afvigelse seneste regning** (%).

Kortet `ha-electricity-bill-card` i [Smart Home Cards](https://github.com/MRDonnii/ha-smart-home-cards) viser det hele og
har en formular til at skrive regningerne ind.

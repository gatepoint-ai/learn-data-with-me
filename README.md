# Learn data with me

**Practical data engineering lessons from 20 years of making numbers reconcile: revenue assurance for telecom operators, star schemas behind finance dashboards, and a 7.8 TB cross-cloud database migration.**

I'm [Maicon Abreu](https://www.linkedin.com/in/mbdabreu/), a senior data engineer with more than 20 years in technology. I've worked on Spark and Kafka pipelines on AWS for telecom clients, dimensional models behind revenue-assurance dashboards, the hands-on engineering of a multi-terabyte PostgreSQL migration, and the Google Cloud environments under a revenue-assurance platform, which I created and deployed in Terraform. Every week I post one note on LinkedIn, and the full version goes up here the same day: what happened, the exact mechanism, the real logs, and something you can run.

## dbt & Snowflake notes

One finding per note from working with dbt and Snowflake: the exact mechanism, the real logs, and something you can run yourself: a dbt project on DuckDB with no account, or a Snowflake test script. New notes every week.

| # | Note | The idea in one line | Example | On LinkedIn |
|---|---|---|---|---|
| 01 | [dbt v2 caught my Snowflake error before Snowflake did](dbt-notes/01-dbt-v2-caught-my-snowflake-error/) | The incremental filter doesn't run until the table exists and the run isn't a full refresh. dbt v2's static analysis flagged the bad token. dbt Core 1.12 doesn't check the SQL it sends. | dbt + DuckDB | [18 Nov 2026](https://lnkd.in/p/dvuDpGQX) |
| 02 | [AUTO picked FULL: a dynamic table's refresh mode](dbt-notes/02-dynamic-table-auto-mode/) | One `current_date()` in the SELECT list made a Snowflake dynamic table on `AUTO` fall back to FULL refresh, with no warning. In the WHERE clause it stayed incremental. Set `refresh_mode` explicitly. | Snowflake SQL | 25 Nov 2026 |

*Watch or star the repo to follow along.*

## Further learning

[RESOURCES.md](RESOURCES.md) lists the free courses and official documentation I recommend. Every link is checked when it's added.

Also by me: [Learn AI with me](https://github.com/gatepoint-ai/learn-ai-with-me), practical lessons from delivering AI systems, and [Argus](https://github.com/gatepoint-ai/learn-ai-with-me/tree/main/argus), the open-source AI app I built.

## A note on the examples

The examples are **teaching material**, written from scratch for these notes, on made-up data. The dbt projects run on DuckDB with no account; the Snowflake scripts create their own database and warehouse and drop them at the end. Real systems I describe are referred to by industry only, with no client names or confidential details.

## License

Code is under the [MIT License](LICENSE). Lesson text and diagrams are under [CC BY 4.0](LICENSE-CONTENT.md): share and adapt them freely with credit.

---

Published by **Gatepoint AI** · Questions or ideas for a note? Open an issue or message me on [LinkedIn](https://www.linkedin.com/in/mbdabreu/).

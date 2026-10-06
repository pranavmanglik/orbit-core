# Database packages

Orbit Core does not include database capability contracts, drivers, adapters, or a built-in
database. Applications install database packages explicitly so the framework runtime stays small
and provider packages own credentials, connections, transactions, failures, and shutdown.

The ecosystem uses this package chain:

```text
orbit-data (database-neutral repository contracts)
    ├── orbit-sql (SQL contract, repositories, units of work)
    │   ├── orbit-sql-sqlite (local and embedded SQLite)
    │   ├── orbit-sql-mysql (MySQL)
    │   └── orbit-sql-postgres (PostgreSQL)
    └── orbit-nosql (NoSQL capability)
        └── provider adapters such as orbit-nosql-mongo
```

Install the packages for the database family and provider that the application uses. SQLite is a
separately installable embedded provider; it is useful for local development and single-process
embedded deployments. It is not a server database or distributed store. SQL transaction and query
behavior belongs to `orbit-sql` and its selected provider. NoSQL providers retain their own query,
consistency, indexing, and transaction limits.

The Core container remains the resource owner. Provider plugins register resources lazily and
Core closes them with the application, without importing any database package itself. See the
`orbit-sql`, `orbit-nosql`, and provider repository guides for API contracts, setup, and limitations.

# carservice-api

[![Java](https://img.shields.io/badge/Java-17-b07219)](https://openjdk.org/projects/jdk/17/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.5-6DB33F?logo=springboot&logoColor=white)](https://spring.io/projects/spring-boot)
[![Tests](https://img.shields.io/badge/tests-30%20passing-brightgreen)](#running-it)
[![OpenAPI](https://img.shields.io/badge/docs-Swagger%20UI-85EA2D?logo=swagger&logoColor=black)](#api)

A REST API for managing a car service / auto workshop: customers, vehicles, a
service catalog, work orders with a mechanic-assignment and status workflow,
and invoicing. Built with Spring Boot 3, Spring Data JPA, and MySQL, with a
full Flyway-managed schema and a layered test suite (unit + Mockito + full
MockMvc integration).

This is a from-scratch reimplementation of the domain from my B.Sc. thesis
project (a PHP/MySQL car-service platform) on a modern Java/Spring stack, to
go with a Serbian junior backend interview process rather than a page of
untested skills.

## Stack

- Java 17, Spring Boot 3.5
- Spring Data JPA / Hibernate, MySQL 8 (Flyway-migrated), H2 for local dev/tests
- Bean Validation, a `@RestControllerAdvice` global error handler
- springdoc-openapi (Swagger UI / OpenAPI 3.1)
- JUnit 5, Mockito, AssertJ, MockMvc
- Docker / docker-compose, GitHub Actions CI

## Domain model

```
Customer 1---* Vehicle 1---* WorkOrder *---1 Mechanic
                                |
                                *---* ServiceType   (via WorkOrderItem, price-snapshotted)
                                |
                                1---1 Invoice
```

- **Customer** — contact details; can't be deleted while they still have vehicles on file.
- **Vehicle** — belongs to a customer; VIN and license plate are unique.
- **ServiceType** — the service catalog (oil change, brake pads, ...) with a base price.
- **Mechanic** — must be `active` to be assigned to a work order.
- **WorkOrder** — the core entity. Owns a status state machine and a list of
  `WorkOrderItem`s (each item snapshots the service's price at the time it was
  added, so later catalog price changes don't retroactively change an open
  work order).
- **Invoice** — generated once a work order is `COMPLETED`; totals are summed
  from the work order's line items, not recomputed from the live catalog.

### Work order status machine

```
RECEIVED --> IN_PROGRESS --> COMPLETED
   |              |
   v              v
CANCELLED     CANCELLED
```

`COMPLETED` and `CANCELLED` are terminal — no further transitions, no adding
or removing items, no reassigning the mechanic. Moving to `IN_PROGRESS`
requires a mechanic to already be assigned; moving to `COMPLETED` requires at
least one service item. This is enforced inside the `WorkOrder` entity itself
(`WorkOrder#transitionTo`), not scattered across the service layer, so the
invariant can't be bypassed by a new code path later.

## Running it

**Quickest path — H2, no setup:**

```bash
./mvnw spring-boot:run
```

Starts on `localhost:8080` with an in-memory H2 database (console at
`/h2-console`), schema created from the JPA mappings. Nothing to install.

**With MySQL, via Docker Compose:**

```bash
docker compose up --build
```

Runs the app against a real MySQL 8 container with the Flyway migrations in
`src/main/resources/db/migration` applied on startup.

**Tests:**

```bash
./mvnw test
```

30 tests: enum transition-matrix tests, entity-level business-rule tests,
Mockito-based service tests, and two `@SpringBootTest` + MockMvc integration
tests — including a full lifecycle test that drives a work order through
every endpoint from creation to a paid invoice against a real (H2) database.

## API

Interactive docs (Swagger UI) are at `/swagger-ui/index.html` once the app is
running, backed by the OpenAPI 3.1 spec at `/v3/api-docs`.

All endpoints are under `/api`. Selected highlights:

| Method | Path | Notes |
|---|---|---|
| `POST` | `/customers` | 409 on duplicate email |
| `DELETE` | `/customers/{id}` | 422 if the customer still has vehicles |
| `POST` | `/vehicles` | 409 on duplicate VIN or plate |
| `POST` | `/work-orders` | creates a `RECEIVED` work order for a vehicle |
| `POST` | `/work-orders/{id}/items` | attach a catalog service, price-snapshotted |
| `POST` | `/work-orders/{id}/mechanic` | 422 if the mechanic is inactive |
| `POST` | `/work-orders/{id}/status` | drives the state machine, 422 on illegal transitions |
| `POST` | `/work-orders/{id}/invoice` | 422 unless `COMPLETED`; 409 if already invoiced |
| `POST` | `/invoices/{id}/pay` | marks paid, stamps `paidAt` |

Errors are a consistent JSON shape (`ApiError`): timestamp, status, message,
request path, and a `fieldErrors` array for validation failures.

## Why these choices

- **Flyway on MySQL, `ddl-auto=create-drop` on H2** — production schema is
  explicit and reviewable, while tests don't pay for migration bookkeeping.
- **Price snapshots on `WorkOrderItem`** — a work order's total shouldn't
  silently change because the shop raised its oil-change price last week.
- **State machine lives on the entity, not the service** — `WorkOrder` can't
  be pushed into an invalid state no matter which code path touches it.

# Reference Notes: Laravel and Docker

**Synthetic test document for the CandiVue knowledge base (written for testing,
not copied from official documentation).**

## Laravel in short

Laravel is a PHP web framework. A typical Laravel developer works with:

- **Routing and controllers** for REST APIs, often with API resources to shape
  JSON responses.
- **Eloquent ORM** for database models, relationships and query scopes. Common
  performance problems are N+1 queries, fixed with eager loading (`with()`).
- **Migrations** to change the database schema in version control.
- **Queues and jobs** for slow work such as emails or reports; Laravel Horizon
  monitors Redis queues.
- **Testing** with PHPUnit or Pest, including feature tests that call the API.
- **Laravel Sail**, a command-line tool that runs a Laravel project in Docker
  containers. Someone who uses Sail day to day is using Docker.

Laravel versions follow PHP closely; current projects run on PHP 8.2 or newer.

## Docker in short

Docker packages an application and everything it needs into an image, which
runs as a container. Words that show real Docker experience:

- writing a **Dockerfile** and building images;
- **Docker Compose** files that start several services together (for example
  PHP-FPM, Nginx, MySQL and Redis);
- running containers in CI pipelines or in production (for example on AWS ECS).

**Podman** runs the same kind of containers and can use the same images, so
Podman experience is a close substitute for Docker. Kubernetes runs containers
at scale and usually means the person also knows Docker.

## Good signs of seniority

- Has improved query or API performance with measured results.
- Has designed database schemas and handled data migrations safely.
- Reviews code and mentors others.
- Can explain trade-offs, for example when to use a queue instead of doing the
  work inside the request.

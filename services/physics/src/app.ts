import Fastify, { type FastifyInstance } from "fastify";
import helmet from "@fastify/helmet";
import cors from "@fastify/cors";
import rateLimit from "@fastify/rate-limit";
import { randomUUID } from "node:crypto";
import { loadEnv, parseOrigins, type Env } from "./config.js";
import { healthRoutes } from "./routes/health.js";

export interface BuildAppOptions {
  readonly env?: Env;
}


export async function buildApp(options: BuildAppOptions = {}): Promise<FastifyInstance> {
  const env = options.env ?? loadEnv();
  const isProduction = env.NODE_ENV === "production";

  const app = Fastify({
    // Cloud Run's logging agent ingests stdout JSON. Pino emits exactly that,

    logger: {
      level: env.LOG_LEVEL,
      messageKey: "message",
      formatters: {
        level: (label) => ({ severity: label.toUpperCase() }),
        bindings: () => ({ service: "physics", version: env.SERVICE_VERSION }),
      },
      // Belt and braces: nothing that could carry a bearer token is ever logged.
      redact: {
        paths: [
          "req.headers.authorization",
          "req.headers.cookie",
          "req.headers['x-goog-iap-jwt-assertion']",
          "res.headers['set-cookie']",
        ],
        remove: true,
      },
    },
    genReqId: () => randomUUID(),
    requestIdHeader: "x-request-id",
    bodyLimit: env.BODY_LIMIT_BYTES,
    // Cloud Run terminates the TLS connection and forwards over HTTP, so
    trustProxy: true,
    disableRequestLogging: false,
  });

  await app.register(helmet, {
    // A JSON API serves no documents, so the strictest possible policy costs
    contentSecurityPolicy: {
      directives: { "default-src": ["'none'"], "frame-ancestors": ["'none'"] },
    },
    hsts: isProduction ? { maxAge: 63_072_000, includeSubDomains: true } : false,
    crossOriginResourcePolicy: { policy: "same-origin" },
  });

  const origins = parseOrigins(env.PHYSICS_ALLOWED_ORIGINS);
  await app.register(cors, {
    // Empty allowlist => every cross-origin request is refused. Correct default.
    origin: origins.length === 0 ? false : origins,
    methods: ["GET", "POST"],
    credentials: false,
    maxAge: 600,
  });

  await app.register(rateLimit, {
    max: env.RATE_LIMIT_MAX,
    timeWindow: env.RATE_LIMIT_WINDOW_MS,
    // In-memory, therefore per-instance. With max-instances=3 the effective
    keyGenerator: (request) => request.ip,
  });

  await app.register(healthRoutes(env));


  app.setErrorHandler((error: unknown, request, reply) => {
    // Fastify 5.12 types the error handler's first argument as `unknown` rather
    // than FastifyError, which is strictly more honest: anything a route throws
    // lands here, including values that are not Errors at all. Narrow it
    // explicitly instead of asserting a shape.
    const statusCode =
      typeof error === "object" &&
      error !== null &&
      "statusCode" in error &&
      typeof error.statusCode === "number"
        ? error.statusCode
        : 500;

    const message = error instanceof Error ? error.message : "Unknown error";

    request.log.error(
      { err: error, requestId: request.id, url: request.url, status: statusCode },
      "request failed",
    );

    // A 4xx from schema validation is safe and useful to echo back in
    // development; in production it is not, and a 5xx never is. A stack trace in
    // an HTTP response is information disclosure, not a debugging convenience.
    const safeMessage =
      statusCode >= 400 && statusCode < 500
        ? isProduction
          ? "Request failed validation"
          : message
        : "Internal error";

    void reply.code(statusCode).send({ error: safeMessage, requestId: request.id });
  });

  app.setNotFoundHandler((request, reply) => {
    void reply.code(404).send({ error: "Not found", requestId: request.id });
  });

  return app;
}

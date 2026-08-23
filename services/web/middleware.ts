import { NextResponse, type NextRequest } from "next/server";


function buildCsp(nonce: string, isDev: boolean): string {
  const directives: Array<[string, string[]]> = [
    ["default-src", ["'self'"]],
   [
      "script-src",
      [
        "'self'",
        `'nonce-${nonce}'`,
        "'strict-dynamic'",
        "'wasm-unsafe-eval'",
        ...(isDev ? ["'unsafe-eval'"] : []),
      ],
    ],

    ["style-src", ["'self'", "'unsafe-inline'"]],


    ["font-src", ["'self'"]],

    ["img-src", ["'self'", "blob:", "data:"]],
    ["media-src", ["'self'", "blob:"]],
    ["worker-src", ["'self'", "blob:"]],
    ["connect-src", ["'self'"]],
    ["frame-ancestors", ["'none'"]],
    ["frame-src", ["'none'"]],
    ["object-src", ["'none'"]],
    ["base-uri", ["'none'"]],
    ["form-action", ["'self'"]],
    ["manifest-src", ["'self'"]],
  ];

  const csp = directives.map(([name, values]) => `${name} ${values.join(" ")}`).join("; ");
  return isDev ? csp : `${csp}; upgrade-insecure-requests`;
}

export function middleware(request: NextRequest): NextResponse {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isDev = process.env.NODE_ENV === "development";
  const csp = buildCsp(nonce, isDev);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("content-security-policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("content-security-policy", csp);
  return response;
}

export const config = {
  matcher: [
   {
      source: "/((?!_next/static|_next/image|favicon.svg).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};

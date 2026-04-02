import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set("ngrok-skip-browser-warning", "true");
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/api/:path*",
};

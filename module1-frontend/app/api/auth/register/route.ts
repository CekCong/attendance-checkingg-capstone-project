import { forwardAuth } from "@/lib/serverAuth";
export async function POST(request: Request) {
  return forwardAuth(request, "register");
}

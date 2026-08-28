import { NextResponse } from "next/server";
import { buildInstructorDashboard } from "@/lib/instructorMock";

export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json(buildInstructorDashboard());
}

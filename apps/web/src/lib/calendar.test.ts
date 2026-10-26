import { describe, expect, it } from "vitest";
import { dateInZone, toUtc } from "./calendar";
import { formatBytes, statusTone } from "./api";
describe("editorial scheduling",()=>{
 it("converts Manaus wall time to UTC",()=>expect(toUtc("2030-05-10T12:00","America/Manaus")).toBe("2030-05-10T16:00:00.000Z"));
 it("handles the previous calendar day",()=>expect(dateInZone("2030-05-10T02:00:00Z","America/Manaus")).toBe("2030-05-09"));
 it("interprets database UTC timestamps explicitly",()=>expect(dateInZone("2030-05-10T02:00:00","America/Manaus")).toBe("2030-05-09"));
 it("rejects daylight-saving gaps",()=>expect(()=>toUtc("2030-03-10T02:30","America/New_York")).toThrow());
 it("distinguishes stopped and failed states",()=>{expect(statusTone("FAILED")).toBe("red");expect(statusTone("WAITING_FOR_AUTH")).toBe("amber");});
 it("reports storage in real units",()=>expect(formatBytes(2097152)).toBe("2.0 MB"));
});

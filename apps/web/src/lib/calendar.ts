export function toUtc(wallTime: string, zone: string): string {
  const desired = new Date(wallTime + "Z");
  if (!Number.isFinite(desired.getTime())) throw new Error("Invalid date");
  const format = new Intl.DateTimeFormat("sv-SE", { timeZone: zone, year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit", hourCycle:"h23" });
  let utc = desired.getTime();
  for (let i=0;i<3;i++) {
    const parts = Object.fromEntries(format.formatToParts(new Date(utc)).map(p=>[p.type,p.value]));
    const represented = Date.UTC(+parts.year,+parts.month-1,+parts.day,+parts.hour,+parts.minute,+parts.second);
    const correction=desired.getTime()-represented;
    if(correction===0) return new Date(utc).toISOString();
    utc+=correction;
  }
  throw new Error("This time does not exist in the selected timezone (daylight saving change)");
}
export function dateInZone(value:string,zone:string) { return new Intl.DateTimeFormat("sv-SE",{timeZone:zone,year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(value.endsWith("Z")||/[+-]\d\d:\d\d$/.test(value)?value:value+"Z")); }

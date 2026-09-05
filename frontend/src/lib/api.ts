import type { components } from "./api-schema";
export type Schema = components["schemas"];
export type Polygon = Schema["PolygonResponse"];
export type Run = Schema["RunResponse"];
export type Point = Schema["DailyPointResponse"];
export type Job = Schema["JobResponse"];
export type Anomaly = Schema["AnomalyResponse"];
export type Session = Schema["SessionResponse"];
export type Capabilities = {limits:Record<string,number>; providers:{id:string;provider:string}[]; supported_period:{from:string;to:string}; active_model:string|null; feature_flags:Record<string,boolean>; retention:{workspace_days:number;export_days:number}};
export type Page<T> = {items:T[];next_cursor:string|null;total:number|null};
export class ApiError extends Error {
  constructor(public status:number,public code:string,message:string,public requestId?:string,public retryable=false){super(message);}
}
let csrf = "";
export function setCsrf(value:string){csrf=value;}
export async function api<T>(path:string,options:RequestInit & {idempotencyKey?:string}={}):Promise<T>{
  const {idempotencyKey,...init}=options;
  const headers=new Headers(init.headers);
  if(init.body) headers.set("Content-Type","application/json");
  if(init.method && !["GET","HEAD"].includes(init.method)) headers.set("X-CSRFToken",csrf);
  if(idempotencyKey) headers.set("Idempotency-Key",idempotencyKey);
  let response:Response;
  try {response=await fetch(`/api/v1/${path}`,{...init,headers,credentials:"same-origin",cache:"no-store"});}
  catch(e){if(e instanceof DOMException && e.name==="AbortError")throw e;throw new ApiError(0,"network_error","Нет соединения с сервером. Проверьте сеть и повторите запрос.",undefined,true);}
  if(!response.ok){const data=await response.json().catch(()=>null);const error=data?.error;if(response.status===401 && typeof window!=="undefined")window.dispatchEvent(new Event("session-expired"));throw new ApiError(response.status,error?.code||"http_error",error?.message||`Ошибка сервера (${response.status})`,error?.request_id,error?.retryable);}
  if(response.status===204)return undefined as T;
  return response.json();
}
export async function allPages<T>(path:string,signal?:AbortSignal):Promise<T[]>{
  const items:T[]=[];let cursor:string|null=null;const seen=new Set<string>();
  do{const page:Page<T>=await api<Page<T>>(`${path}${path.includes("?")?"&":"?"}limit=100${cursor?`&cursor=${encodeURIComponent(cursor)}`:""}`,{signal});items.push(...page.items);cursor=page.next_cursor;if(cursor&&seen.has(cursor))throw new Error("Сервер повторил курсор страницы");if(cursor)seen.add(cursor);}while(cursor);
  return items;
}
export const terminalJob=(state:string)=>["succeeded","failed","cancelled"].includes(state);
export const terminalRun=(state:string)=>["completed","partial","no_data","failed","cancelled"].includes(state);
export const label:Record<string,string>={queued:"В очереди",running:"Выполняется",completed:"Завершён",partial:"Частичные данные",no_data:"Нет данных",failed:"Ошибка",cancelled:"Отменён",succeeded:"Готово",normal:"Без выявленного стресса",stress:"Стресс",critical:"Критично",insufficient_data:"Недостаточно данных",observed:"Наблюдение",interpolated:"Интерполяция",extrapolated:"Экстраполяция",climatology_fallback:"Сезонная оценка",unavailable:"Недоступно",validating:"Проверка",discovering:"Поиск контуров",fetching_satellite:"Спутниковые снимки",fetching_weather:"Погодные данные",preprocessing:"Очистка данных",reconstructing:"Восстановление NDVI",detecting:"Поиск аномалий",exporting:"Подготовка файла",low:"Низкая",medium:"Средняя",high:"Высокая"};
export function number(value:number|null|undefined,digits=3){return value==null?"—":value.toLocaleString("ru-RU",{maximumFractionDigits:digits});}

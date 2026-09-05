import {afterEach,describe,it,expect,vi} from "vitest";
import {api,allPages,setCsrf,ApiError} from "../../src/lib/api";
afterEach(()=>vi.unstubAllGlobals());
describe("API transport",()=>{
 it("передаёт CSRF и idempotency key без автоматического повтора",async()=>{const fetch=vi.fn().mockResolvedValue(Response.json({ok:true}));vi.stubGlobal("fetch",fetch);setCsrf("token");await api("analyses",{method:"POST",body:"{}",idempotencyKey:"stable-key"});const init=fetch.mock.calls[0][1];expect(init.headers.get("X-CSRFToken")).toBe("token");expect(init.headers.get("Idempotency-Key")).toBe("stable-key");expect(init.credentials).toBe("same-origin");expect(fetch).toHaveBeenCalledTimes(1);});
 it("сохраняет код и request_id ошибки",async()=>{vi.stubGlobal("fetch",vi.fn().mockResolvedValue(Response.json({error:{code:"version_conflict",message:"Конфликт версий",request_id:"trace"}},{status:409})));await expect(api("polygons/1")).rejects.toMatchObject({status:409,code:"version_conflict",requestId:"trace"});});
 it("не превращает сетевой сбой в пустые данные",async()=>{vi.stubGlobal("fetch",vi.fn().mockRejectedValue(new TypeError("offline")));await expect(api("polygons")).rejects.toBeInstanceOf(ApiError);});
 it("собирает все страницы",async()=>{const fetch=vi.fn().mockResolvedValueOnce(Response.json({items:[1],next_cursor:"next"})).mockResolvedValueOnce(Response.json({items:[2],next_cursor:null}));vi.stubGlobal("fetch",fetch);expect(await allPages("polygons")).toEqual([1,2]);expect(fetch.mock.calls[1][0]).toContain("cursor=next");});
});

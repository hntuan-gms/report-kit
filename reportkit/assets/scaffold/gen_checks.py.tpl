# -*- coding: utf-8 -*-
"""Writes checks.yaml (UI entries) of the screen group hosted by workspace {code}.
Run: python gen_checks.py ; rt check {code} --pending      (background, one completion wait; never poll)
Selectors: open the screen's .html first. Onboarding tours / banners are removed by the profile's ui.pre_steps."""
import json
import yaml

PAGE = "/CHANGE/ME"
READY = {"selector": "app-table tbody tr", "min": 1, "timeout": 60000}
TRAP = {"js": "()=>{window.__dlg=[];window.alert=m=>window.__dlg.push('alert:'+m);window.confirm=m=>{window.__dlg.push('confirm:'+m);return false};window.prompt=m=>{window.__dlg.push('prompt:'+m);return null}}"}
SEARCH = {"click": "button[type=submit]"}                 # CHANGE: the search button
ABORT_WRITES = []                                          # e.g. [{"pattern": "**/send-*", "abort": True}] for every non-GET the screen can send

JS = {
    "title": '()=>(document.querySelector(".card-title, h4")||{}).innerText||null',
    "labels": '()=>[...document.querySelectorAll("label")].map(l=>(l.innerText||"").replace(/\\s+/g," ").trim())',
    "heads": '()=>[...document.querySelectorAll("app-table thead th")].map(t=>(t.innerText||"").replace(/\\s+/g," ").trim())',
    "rows": '()=>[...document.querySelectorAll("app-table tbody tr")].map(r=>[...r.querySelectorAll("td")].map(td=>(td.innerText||"").replace(/\\s+/g," ").trim()))',
    "pager": '()=>{const p=document.querySelector(".p-paginator");return p?(p.innerText||"").replace(/\\s+/g," ").trim():null}',
    "inputs": '()=>[...document.querySelectorAll("input")].filter(i=>i.offsetParent!==null).map(i=>i.value)',
    "injected": '()=>({scripts:document.querySelectorAll("app-table script").length,imgs:document.querySelectorAll("app-table img[onerror]").length,svgs:document.querySelectorAll("app-table svg[onload]").length,title:document.title})',
    "dlg": '()=>window.__dlg||[]',
    "overflow": '()=>document.documentElement.scrollWidth>window.innerWidth+2',
}


def FIELD(sel, text):
    """Type into an input the way Angular sees it (value setter + input/change/blur events)."""
    return {"js": "()=>{const i=document.querySelector(%s);if(!i)return false;Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(i,%s);['input','change','blur'].forEach(e=>i.dispatchEvent(new Event(e,{bubbles:true})));return true}" % (json.dumps(sel), json.dumps(text))}


def obs(*names, **extra):
    o = {n: {"js": JS[n]} for n in names}
    o.update(extra)
    return o


ui = []


def U(id, title, steps=None, observe=None, page=None, ready=None, **kw):
    u = {"id": id, "title": title, "page": page or PAGE, "ready": ready or READY}
    u.update(kw)
    if steps:
        u["steps"] = steps
    u["observe"] = dict(observe or {})
    u["observe"].setdefault("calls", "requests")      # `rt show` hides the noise requests
    u["observe"].setdefault("toasts", "toasts")
    ui.append(u)


W = {"wait": 1500}
U("U01", "Open the screen: title, labels, columns, first rows, pager", [W], obs("title", "labels", "heads", "rows", "pager", "overflow", url="url"))
U("U02", "English mode: title, labels, columns, data", [W, {"set_lang": "en"}, {"wait": 3500}], obs("title", "labels", "heads", "rows", "pager"))
U("U03", "No result: grid message and pager", [W, FIELD("input", "zzzzqq"), SEARCH, {"wait": 2500}], obs("rows", "pager"))
U("U04", "Page 2: row numbers continue", [W, {"click": ".p-paginator button.p-paginator-next"}, {"wait": 2500}], obs("rows", "pager"))
U("U05", "XSS typed in a filter", [W, TRAP, FIELD("input", "<script>alert('xss1')</script>"), SEARCH, {"wait": 2500}], obs("rows", "inputs", "injected", "dlg"))
# routes: go at ENTRY level so the stub is in place before the page loads (a route step after `ready` misses the first requests)
U("U06", "Simulated 500 on load: a message, or does it look like 'no data'?", [{"wait": 2500}], obs("rows", "pager"),
  routes=[{"pattern": "**/CHANGE-ME?*", "status": 500, "body": '{"success":false,"message":"Simulated"}'}])
U("U07", "Stubbed data with script strings is shown as text", [TRAP, {"wait": 2500}], obs("rows", "injected", "dlg"),
  routes=[{"pattern": "**/CHANGE-ME?*", "status": 200, "body": json.dumps({"success": True, "data": {"content": [{"id": 1, "name": "<img src=x onerror=alert('d1')>"}], "totalElements": 1, "totalPages": 1, "size": 10, "number": 0}})}])

with open("checks.yaml", "w", encoding="utf-8") as f:
    yaml.safe_dump({"system": "{system}", "ui": ui}, f, allow_unicode=True, sort_keys=False, width=300)
print("ui entries:", len(ui))

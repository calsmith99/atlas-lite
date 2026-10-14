"""Optional browser check: pip install playwright; playwright install chromium.
Uses fixture traffic only; never starts Claude, edits a vault, or touches a live Atlas.
"""
import asyncio
import os
from pathlib import Path
from aiohttp import web
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]

async def main():
    sockets, requests = [], []
    reject_next = [False]
    meta = {'id':'fixture','last':1,'title':'Work session','cwd':'/work/project','working':True,'driving':True,'pending':False}
    runtime = {'status':{'fixture':{'stage':'working','text':'Reading project files'}},'permissions':[], 'usage':{'fixture':{'input':123,'output':45,'cached':1000,'at':1,'cost':.012}},'usageWindows':{'five_hour':{'utilization':.32,'resetsAt':2000000000}}}
    history = [{'kind':'user','text':'Check this project.'},{'kind':'claude','text':'A safe command to copy.\n```sh\ngit status --short\n```'}]
    async def emit(msg):
        for ws in sockets:
            await ws.send_json(msg)
    async def ws_handler(req):
        ws=web.WebSocketResponse();await ws.prepare(req);sockets.append(ws)
        await ws.send_json({'t':'hello','sessions':[meta], 'touches':[], 'runtime':runtime})
        async for _ in ws: pass
        sockets.remove(ws)
        return ws
    async def api(req):
        if req.method=='POST':
            requests.append((req.path, await req.json()))
            if reject_next[0]:
                reject_next[0] = False
                return web.json_response({'error':'Fixture send rejected'}, status=409)
            return web.json_response({'ok':True})
        if req.path=='/api/config':
            return web.json_response({'graphs':[{'id':'notes','label':'Notes'}], 'addons':[], 'voice':False})
        if req.path.startswith('/api/graph/'):
            return web.json_response({'nodes':[{'id':'note.md','name':'Example note','folder':'Reference'}], 'links':[]})
        if req.path.endswith('/preview'):
            return web.json_response({'name':'note.md','kind':'markdown','text':'# Preview works\n<script>window.bad=true</script>'})
        return web.json_response({'session':meta,'history':history,'runtime':runtime})
    app=web.Application()
    app.router.add_get('/',lambda r:web.FileResponse(ROOT/'dashboard/index.html'))
    app.router.add_get('/ws',ws_handler)
    app.router.add_route('*','/api/{tail:.*}',api)
    app.router.add_static('/static/',ROOT/'dashboard')
    runner=web.AppRunner(app);await runner.setup()
    site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    port=site._server.sockets[0].getsockname()[1]
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,args=['--enable-unsafe-swiftshader'])
            page=await browser.new_page(viewport={'width':1920,'height':1080},ignore_https_errors=True)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(f'http://127.0.0.1:{port}')
            await page.locator('#draft:not([disabled])').wait_for(timeout=30000)
            assert not await page.locator('#preview').is_visible(), 'Hidden frame leaked into initial page'
            assert await page.locator('#stop').is_visible()
            assert await page.locator('#send').inner_text()=='Send correction'
            await page.locator('#draft').fill('Use the existing helper instead')
            await page.locator('#send').click()
            assert requests[-1]==('/api/session/fixture/interrupt',{'text':'Use the existing helper instead'})
            await page.locator('#stop').click()
            assert requests[-1]==('/api/session/fixture/interrupt',{})
            await page.get_by_text('Copy code…',exact=True).click()
            assert await page.locator('#artifact-body pre').inner_text()=='git status --short\n'
            await page.locator('#close-preview').click()
            p={'t':'permission','id':'q1','session':'fixture','tool':'AskUserQuestion','input':{'questions':[{'question':'Which approach?', 'options':[{'label':'Use helper','description':'Reuse the current implementation'},{'label':'New helper'}]}]}}
            await emit(p)
            await page.get_by_text('Use helper — Reuse the current implementation',exact=True).click()
            await page.get_by_role('button',name='Continue',exact=True).click()
            assert requests[-1][1]['answers']=={'Which approach?':'Use helper'}
            p={'t':'permission','id':'p1','session':'fixture','tool':'Bash','description':'Run project checks','input':{'command':'make check'}}
            runtime['permissions']=[p];await emit(p)
            await page.get_by_role('button',name='Allow once').wait_for()
            await page.reload()
            await page.get_by_role('button',name='Allow once').wait_for()
            await page.get_by_role('button',name='Deny',exact=True).click()
            assert requests[-1][1]['allow'] is False
            runtime['permissions']=[]
            await page.locator('#open-file').click()
            await page.locator('.file-form input').fill('note.md')
            await page.get_by_role('button',name='Open',exact=True).click()
            await page.get_by_role('heading',name='Preview works').wait_for()
            assert not await page.evaluate('Boolean(window.bad)'), 'Markdown ran a script'
            # Pasting stages an actual clipboard image; it never sends automatically.
            png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB68AAAAASUVORK5CYII='
            async def paste_image():
                await page.locator('#draft').evaluate("""(el,data) => {
                  const bytes = Uint8Array.from(atob(data), c=>c.charCodeAt(0));
                  const clipboardData = new DataTransfer();
                  clipboardData.items.add(new File([bytes],'screenshot.png',{type:'image/png'}));
                  el.dispatchEvent(new ClipboardEvent('paste',{clipboardData,bubbles:true,cancelable:true}));
                }""", png)
                await page.locator('#attachments img').wait_for()
                await page.locator('#send:not([disabled])').wait_for()
            before = len(requests)
            await paste_image()
            assert len(requests)==before
            await page.get_by_role('button',name='Remove screenshot.png').click()
            assert not await page.locator('#attachments').is_visible()
            await paste_image()
            await page.locator('#draft').fill('See screenshot')
            await page.locator('#send').click()
            assert requests[-1][0].endswith('/interrupt')
            assert requests[-1][1]['images'][0]['data']==png
            assert requests[-1][1]['text']=='See screenshot'
            await page.locator('#attachments').wait_for(state='hidden')
            meta.update(working=False,driving=False)
            await emit({'t':'session','session':meta})
            await paste_image()
            reject_next[0] = True
            await page.locator('#send').click()
            await page.get_by_text('Fixture send rejected', exact=True).wait_for()
            assert await page.locator('#attachments img').is_visible(), 'Failed send lost the image draft'
            await page.locator('#send:not([disabled])').wait_for()
            await page.locator('#send').click()  # image without accompanying text
            await page.locator('#attachments').wait_for(state='hidden')
            assert requests[-1][0].endswith('/send')
            assert requests[-1][1]['text']==''
            assert requests[-1][1]['images'][0]['media_type']=='image/png'
            await emit({'t':'entry','session':'fixture','entry':{'kind':'user','text':'','images':[requests[-1][1]['images'][0]]}})
            await page.locator('.sent-image').wait_for()
            await page.locator('.sent-image').click()
            assert await page.locator('#artifact-body img').is_visible()
            # Desktop review frame clears both sidebars and the title.
            for width,height in [(1920,1080),(1280,800),(1024,768)]:
                await page.set_viewport_size({'width':width,'height':height})
                bounds=await page.evaluate('''() => Object.fromEntries(['left','right','preview','title'].map(id=>{let r=document.getElementById(id).getBoundingClientRect(); return [id,{left:r.left,right:r.right,top:r.top,bottom:r.bottom}]}))''')
                assert bounds['preview']['left']>=bounds['left']['right']
                assert bounds['preview']['right']<=bounds['right']['left']
                assert bounds['preview']['top']>=bounds['title']['bottom']
            await page.set_viewport_size({'width':1920,'height':1080})
            await page.wait_for_function('document.querySelector("#globe canvas").width <= innerWidth*devicePixelRatio')
            await page.wait_for_timeout(250)
            if output := os.environ.get('ATLAS_TEST_SCREENSHOT'):
                await page.screenshot(path=output)
            await page.set_viewport_size({'width':390,'height':844})
            await page.wait_for_function('document.querySelector("#globe canvas").width <= innerWidth*devicePixelRatio')
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth'), await page.evaluate('''() => [...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().right])''')
            assert not errors, errors
            print('Browser passed: image paste/remove, image-only send, image corrections, failed-send retention, sent-image preview, controls and responsive layout.')
            await browser.close()
    finally:
        await runner.cleanup()

if __name__=='__main__': asyncio.run(main())

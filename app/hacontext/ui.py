"""English, keyboard/mouse-operated terminal interface shared by Linux and HA OS."""
from __future__ import annotations
import asyncio
import dataclasses
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from typing import Callable

from prompt_toolkit import Application
from prompt_toolkit.application import run_in_terminal
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (Layout, HSplit, VSplit, Window, DynamicContainer,
                                  ConditionalContainer, ScrollablePane, Dimension)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Label, Button, TextArea, RadioList, Checkbox, Frame, Box, SearchToolbar
from . import __version__
from .state import (Store, Settings, safe_text, safe_error, discover_containers, choose_endpoint,
                    diagnostics, legacy_candidates, remove_legacy, compare_exports, private_replace,
                    source_archive)

STYLE=Style.from_dict({
    '':'bg:#18232c #e3dccf', 'brand':'bg:#18232c #b2a1ce bold',
    'header':'bg:#18232c #9bbfd3', 'frame.border':'#445966', 'frame.label':'#b2a1ce bold',
    'sidebar':'bg:#20303b #a9b7c2', 'body':'bg:#23313c #e3dccf',
    'label':'#e3dccf', 'muted':'#96a9b7', 'title':'#c4b7df bold',
    'button':'bg:#304654 #d6e4ec', 'button.focused':'bg:#9bbfd3 #172530 bold',
    'button.arrow':'#d8b26e', 'text-area':'bg:#17252f #e3dccf',
    'text-area focused':'bg:#1b303e', 'radio-list':'bg:#23313c',
    'radio-selected':'#9bbfd3 bold', 'radio-checked':'#d8b26e',
    'checkbox':'#d8b26e', 'checkbox-selected':'#9bbfd3 bold',
    'status':'bg:#30414c #d8b26e', 'footer':'bg:#152029 #96a9b7',
    'search-toolbar':'bg:#304654 #ffffff', 'scrollbar.background':'bg:#283945',
    'scrollbar.button':'bg:#839ead',
})


class ContextUI:
    def __init__(self, store: Store, *, input=None, output=None):
        self.store=store
        self.controls={}
        self.page=''; self.heading='';self.subtitle=''
        self.message='';self.busy=False;self.process=None
        self.detected=[];self.pending=Settings();self.pending_token='';self.checks=[]
        self.uninstall_requested=False; self.closing=False
        self.job=None;self.job_id=0
        self.body=HSplit([Label('Loading…')]);self.side=HSplit([])
        self.initial_error=''
        try:self.settings=store.load()
        except ValueError as exc:self.settings=None;self.initial_error=str(exc)
        self.onboarding=self.settings is None
        if self.settings:self.pending=dataclasses.replace(self.settings)
        if store.addon:
            self.pending=Settings(url='http://supervisor',source_mode='local',
                 source_dir='/homeassistant_config',supervisor=True)
            if self.settings:self.pending=dataclasses.replace(self.settings)
        bindings=KeyBindings()
        @bindings.add('tab')
        def next_focus(event):event.app.layout.focus_next()
        @bindings.add('s-tab')
        def prev_focus(event):event.app.layout.focus_previous()
        @bindings.add('c-q')
        def quit_app(event):self.quit()
        @bindings.add('f1')
        def help_app(event):
            if not self.busy:self.docs()
        @bindings.add('f2')
        def home_app(event):
            if not self.busy:self.overview() if self.settings else self.welcome()
        @bindings.add('c-c')
        def interrupt(event):
            if self.busy:self.cancel_job()
            else:self.quit()
        root=HSplit([
            Window(FormattedTextControl([('class:brand','  ha-context'),('class:header','   /   HOME ASSISTANT INVENTORY'),
                                        ('class:muted','   '+__version__)]),height=1),
            Window(FormattedTextControl('  HA  ── read ──  REVIEW  ── save ──  TXT / ZIP'),height=1,style='class:muted'),
            VSplit([
                Box(DynamicContainer(lambda:self.side),padding=1,width=Dimension.exact(25),style='class:sidebar'),
                Frame(HSplit([
                    Window(FormattedTextControl(lambda:[('class:title',self.heading)]),height=1),
                    Label(lambda:safe_text(self.subtitle),style='class:muted'),
                    Window(height=1),
                    DynamicContainer(lambda:self.body),
                ]),title='Workspace',style='class:body')
            ]),
            Window(FormattedTextControl(lambda:safe_text(' '+self.message)),height=2,wrap_lines=True,style='class:status'),
            Window(FormattedTextControl(' Tab / Shift-Tab: move   Enter / Space: choose   F1: help   F2: home   Ctrl-Q: quit'),height=1,style='class:footer'),
        ])
        self.app=Application(layout=Layout(root),key_bindings=bindings,style=STYLE,
            full_screen=True,mouse_support=True,input=input,output=output)
        self.sidebar()
        if self.initial_error:self.recovery()
        elif self.settings:self.overview()
        else:self.welcome()

    def button(self,text,handler,name=None):
        # Stable text and handler names let tests exercise real UI controls.
        def guarded():
            if self.busy and name!='cancel':
                self.set_message('A task is running. Cancel it before leaving this screen.');return
            try:handler()
            except Exception as exc:self.set_message(safe_error(exc))
        button=Button(text=text,handler=guarded,width=max(12,min(30,len(text)+4)))
        if name:self.controls[name]=button
        return button

    def row(self,*buttons):
        return VSplit(list(buttons)+[Window()],padding=1,height=1)

    def field(self,name,label,value='',*,password=False,height=1):
        area=TextArea(text=str(value),multiline=height>1,password=password,height=height,
                      scrollbar=height>1,wrap_lines=height>1,name=name)
        self.controls[name]=area
        return HSplit([Label(label,style='class:muted'),area],padding=0)

    def select(self,name,values,default=None):
        value=RadioList(values,default=default,show_scrollbar=True)
        self.controls[name]=value
        return value

    def check(self,name,label,value=False):
        c=Checkbox(label,checked=value);self.controls[name]=c;return c

    def sidebar(self):
        if self.onboarding:
            steps=['Welcome','Connection','Configuration source','Privacy & notes','Ready']
            widgets=[Label('FIRST RUN',style='class:muted'),Window(height=1)]
            for n,text in enumerate(steps,1):widgets.append(Label(f'{n}  {text}'))
            widgets.extend([Window(height=1),self.button('Documentation',self.docs),Window(height=1),
                            self.button('Maintenance',self.maintenance),Window()])
        else:
            widgets=[Label('YOUR WORKSPACE',style='class:muted'),Window(height=1)]
            for label,action in [('Overview',self.overview),('Create export',self.export_page),
                    ('Devices & sensors',self.inventory),('Export history',self.history),
                    ('Diagnostics',self.diagnostics_page),('Notes',self.notes_page),
                    ('Documentation',self.docs),('Settings',self.settings_page),('Maintenance',self.maintenance)]:
                widgets.extend([self.button(label,action),Window(height=1)])
            widgets.append(Window())
        widgets.append(self.button('Exit',self.quit))
        self.side=ScrollablePane(HSplit(widgets),show_scrollbar=False,max_available_height=80)

    def show(self,page,title,subtitle,widgets,focus=None,*,scroll=True):
        self.page=page;self.heading=title;self.subtitle=subtitle
        self.body=ScrollablePane(HSplit(widgets+[Window(height=1)],padding=1)) if scroll else HSplit(widgets,padding=1)
        self.message=''
        try:
            if focus:self.app.layout.focus(focus)
            else:self.app.layout.focus_next()
        except ValueError:pass
        self.app.invalidate()

    def set_message(self,message):
        self.message=safe_text(message);self.app.invalidate()

    def text_view(self,text,height=None,*,name='viewer',search=True):
        toolbar=SearchToolbar() if search else None
        area=TextArea(text=safe_text(text),read_only=True,scrollbar=True,wrap_lines=False,
                      search_field=toolbar,height=height)
        self.controls[name]=area
        return HSplit([area,toolbar] if toolbar else [area])

    def welcome(self):
        self.onboarding=True;self.sidebar()
        start=self.button('Start setup',self.connection,name='start')
        rows=[Label('Your smart home, ready for a conversation.',style='class:title'),
              Label('Collect real entities, phone sensors and configuration into a\nreviewable file. The program never controls your devices.'),
              Frame(Label('READ ONLY\nNo AI connection. No upload. No always-on Linux service.\n\nKEEP CONTROL\nReview the snapshot before sharing it with a chat.'),title='What happens here'),
              Label('Program folder: '+safe_text(self.store.root)+'\nPrivate files: '+safe_text(self.store.local),style='class:muted'),
              self.row(start,self.button('Read the guide',self.docs))]
        legacy=legacy_candidates(Path.home(),self.store.root) if not self.store.addon else []
        if legacy:rows.append(self.button(f'Review old files ({len(legacy)})',self.legacy_page,name='legacy'))
        self.show('welcome','Welcome to ha-context','A short setup. Then one command, one workspace.',rows,start)

    def recovery(self):
        self.show('recovery','Settings need attention',self.initial_error,[
            Label('Your exports and notes have not been modified.'),
            self.button('Reset settings',self.reset_confirm),self.button('Documentation',self.docs)])

    def connection(self):
        self.controls={}
        p=self.pending
        rows=[]
        if self.store.addon:
            rows+=[Label('Home Assistant OS app detected.',style='class:title'),
                   Label('The Supervisor supplies authentication internally.\nNo personal token is needed or saved.\nThe configuration mount is read-only.')]
        else:
            rows+=[self.field('url','Home Assistant URL',p.url),
                   self.field('token','Long-Lived Access Token (hidden)',self.pending_token,password=True),
                   Label('Create it in HA: User profile → Security → Long-Lived Access Tokens.\nNever send the token to a chat. Leave blank to keep your saved token.',style='class:muted'),
                   self.row(self.button('Detect local HA',self.detect,name='detect'),
                            self.button('Authorize Docker',self.authorize_docker,name='authorize'))]
        rows+=[self.row(self.button('Test & continue',lambda:self.schedule(self.connection_next()),name='next'),
                       self.button('Back',self.welcome))]
        self.show('connection','Connect to Home Assistant','Automatic discovery, or your chosen local/remote address.',rows,
                  self.controls.get('url') or self.controls['next'])

    def capture_connection(self):
        if not self.store.addon:
            entered_url=self.controls['url'].text.strip()
            if entered_url != self.pending.url:self.pending.auto_url=False
            self.pending.url=entered_url
            entered=self.controls['token'].text.strip()
            if entered:self.pending_token=entered
            if not self.pending_token and self.settings:
                self.pending_token=self.store.token()
            if not self.pending_token:raise ValueError('Paste your own HA access token to continue.')
            from .engine import normalize_url
            self.pending.url=normalize_url(self.pending.url)

    async def connection_next(self):
        try:
            self.capture_connection()
            from .state import client_for
            token=os.environ.get('SUPERVISOR_TOKEN','') if self.store.addon else self.pending_token
            if not token:raise ValueError('Supervisor token is missing. Check the HA OS app configuration.')
            self.busy=True;self.set_message('Checking your selected address...')
            def probe():
                c=client_for(self.pending,token)
                try:
                    config=c.get('/api/config')
                    try:c.ws_request('config/entity_registry/list');ws='OK'
                    except Exception as exc:ws=safe_error(exc,token)
                    return config,ws
                finally:c.close()
            config,ws=await asyncio.to_thread(probe)
            self.checks=[{'check':'REST API','status':'OK','detail':'HA '+str(config.get('version'))},
                         {'check':'WebSocket','status':'OK' if ws=='OK' else 'PARTIAL','detail':ws}]
            self.pending.label=str(config.get('location_name') or 'Home Assistant')
            self.busy=False
            self.source_page()
            if ws!='OK':self.set_message('REST works; WebSocket needs attention. A readable config source can supply registry fallbacks.')
        except Exception as exc:
            self.busy=False;self.set_message(safe_error(exc,self.pending_token))

    def schedule(self,coro):
        self.app.create_background_task(coro)

    def detect(self):
        # Preserve partially entered credentials while detection switches screens.
        if self.page=='connection':
            self.pending.url=self.controls.get('url').text if self.controls.get('url') else self.pending.url
            if self.controls.get('token') and self.controls['token'].text:self.pending_token=self.controls['token'].text.strip()
        self.schedule(self.detect_async())

    async def detect_async(self):
        self.busy=True;self.set_message('Looking for Home Assistant in local container runtimes...')
        try:
            rows,issues=await asyncio.to_thread(discover_containers,self.pending.docker_sudo)
            self.detected=rows;self.busy=False
            if not rows:
                self.set_message(' '.join(issues) or 'No local HA container detected. Enter its URL, or use API-only mode for a remote installation.');return
            if len(rows)==1:self.use_container(rows[0]);return
            pick=self.select('detected',[(str(i),safe_text(r['name']+' · '+r['runtime'])) for i,r in enumerate(rows)],'0')
            self.show('detected','Choose your Home Assistant','Only your selection receives the access token.',[
                pick,self.button('Use selected',lambda:self.use_container(rows[int(pick.current_value)])),self.button('Back',self.connection)],pick)
        except Exception as exc:self.busy=False;self.set_message(safe_error(exc))

    def use_container(self,row):
        self.pending.source_mode='container';self.pending.container=row['name'];self.pending.runtime=row['runtime']
        self.pending.docker_sudo=row.get('docker_sudo',False)
        self.pending.url=choose_endpoint(row);self.pending.auto_url=True
        self.connection();self.set_message('Selected '+row['name']+'. Its local address will be refreshed from Docker before exports.')

    def authorize_docker(self):self.schedule(self.authorize_async())

    async def authorize_async(self):
        if not shutil.which('sudo'):
            self.set_message('sudo is not installed. Use an account with container access, a readable folder, or API only.');return
        result=await run_in_terminal(lambda:subprocess.run(['sudo','-v'],check=False).returncode)
        if result:
            self.set_message('Authorization was not granted. Nothing changed.');return
        self.pending.docker_sudo=True
        self.detect()

    def source_page(self):
        p=self.pending
        options=[('container','Local Docker / Podman container'),('local','Readable configuration folder'),('api','API only (remote HA / no file access)')]
        mode=self.select('source_mode',options,p.source_mode)
        choices=[('', 'No container selected')]+[(r['name'],safe_text(r['name']+' · '+r['runtime'])) for r in self.detected]
        if p.container and p.container not in {k for k,v in choices}:choices.append((p.container,p.container))
        container=self.select('container',choices,p.container)
        folder=self.field('source_dir','Configuration folder (for local folder mode)',p.source_dir)
        auto=self.check('auto_url','Refresh the selected container’s local address before each export',p.auto_url)
        rows=[mode,Frame(container,title='Container'),folder,auto,
            Label('API-only mode includes phone sensors and registries when permitted,\nbut cannot provide local YAML files or includes.',style='class:muted'),
            self.row(self.button('Continue',self.source_next,name='source-next'),self.button('Back',self.connection))]
        self.show('source','Choose the configuration source','Verify this source belongs to the SAME HA instance as the URL.',rows,mode)

    def source_next(self):
        p=self.pending
        p.source_mode=self.controls['source_mode'].current_value
        p.container=self.controls['container'].current_value
        p.source_dir=self.controls['source_dir'].text.strip()
        p.auto_url=self.controls['auto_url'].checked and p.source_mode=='container'
        if p.source_mode=='local':
            src=Path(p.source_dir).expanduser()
            if not (src/'configuration.yaml').is_file():raise ValueError('That folder does not contain configuration.yaml.')
            if self.store.root.resolve().is_relative_to(src.resolve()) or src.resolve().is_relative_to(self.store.root.resolve()):
                raise ValueError('Program files and HA configuration must be separate folders.')
            p.source_dir=str(src.resolve())
        p.validate();self.privacy_page()

    def privacy_page(self):
        p=self.pending
        notes=self.store.notes.read_text() if self.store.notes.exists() else ''
        if getattr(self,'draft_notes',None) is not None:notes=self.draft_notes
        rows=[Label('Known credential and location fields are masked.',style='class:title'),
            Label('Names, room layout and presence remain. Review every export before sharing.\nLeave extra network masking off when you need real Wi-Fi names in rules.'),
            self.check('network_privacy','Also mask network addresses and Wi-Fi readings',p.network_privacy),
            self.check('device_details','Collect device trigger / condition / action descriptions',p.device_details),
            self.field('retention','Keep the most recent exports (0 = keep all)',p.retention),
            self.field('notes','Optional notes for future chats (physical setup, external apps)',notes,height=5),
            self.row(self.button('Continue',self.privacy_next,name='privacy-next'),self.button('Back',self.source_page))]
        self.show('privacy','Privacy & context','Choose what remains useful, and add what HA cannot know.',rows,self.controls['network_privacy'])

    def privacy_next(self):
        self.pending.network_privacy=self.controls['network_privacy'].checked
        self.pending.device_details=self.controls['device_details'].checked
        try:self.pending.retention=int(self.controls['retention'].text)
        except ValueError:raise ValueError('Retention must be a whole number.')
        self.pending.validate();self.draft_notes=self.controls['notes'].text
        self.ready_page()

    def ready_page(self):
        p=self.pending
        details=f'INSTANCE      {safe_text(p.label)}\nADDRESS       '+('Supervisor internal proxy' if p.supervisor else safe_text(p.url))
        details+=f'\nSOURCE        {p.source_mode}\nCONTAINER     {p.container or "—"}\nCONFIG FILES  {p.source_dir or ("inside the selected container" if p.source_mode=="container" else "not selected")}\n'
        details+=f'\nPRIVATE DATA  {self.store.local}\nEXPORTS       {self.store.exports}\nKEEP          {p.retention or "all"}\n'
        details+='\nAuthentication stays local. No export has run yet.'
        save=self.button('Save & open',lambda:self.schedule(self.finish_setup()),name='finish')
        self.show('ready','Ready when you are','Check the selected instance before saving.',[Label(details),self.row(save,self.button('Back',self.privacy_page))],save)

    async def finish_setup(self):
        try:
            self.pending.validate()
            self.store.save(self.pending,None if self.pending.supervisor else (self.pending_token or None))
            private_replace(self.store.notes,getattr(self,'draft_notes',''))
            self.settings=dataclasses.replace(self.pending)
            self.pending_token='';self.onboarding=False;self.sidebar();self.overview()
            if not self.store.addon:
                await self.install_command()
        except Exception as exc:self.set_message(safe_error(exc))

    async def install_command(self):
        if self.store.addon:return
        from .maintenance import command_path, install_link
        try:
            path=command_path()
            needs_sudo=not os.access(path.parent if path.parent.exists() else path.parent.parent,os.W_OK)
            if needs_sudo:
                result=await run_in_terminal(lambda:subprocess.run(['sudo','-v'],check=False).returncode)
                if result:raise ValueError('Command shortcut authorization declined. The app itself is configured.')
            await asyncio.to_thread(install_link,self.store,path,needs_sudo)
            self.set_message('Saved. Next time, run ha-context. No flags or setup commands are needed.')
        except Exception as exc:self.set_message(safe_error(exc))

    def overview(self):
        if not self.settings:self.welcome();return
        history=self.store.history()
        if history:
            summary=json.loads((history[0]/'summary.json').read_text())
            text=f"LAST SNAPSHOT   {summary.get('status','Unknown')}\n\n{summary.get('live_entities','?')} live entities    {summary.get('registered_entities','?')} registry entries\n{summary.get('devices','?')} devices          {summary.get('companion_registrations','?')} phone registrations\n\n{summary.get('snapshot_finished_utc','')}\nScope: {summary.get('scope','unknown')}\nDistinct issues: {summary.get('warning_count','?')}"
        else:text='No snapshot yet.\n\nCreate your first export to browse devices, phone sensors\nand configuration. No device actions will run.'
        rows=[Frame(Label(text),title='Snapshot'),
            self.row(self.button('Create export',self.export_page,name='export'),self.button('Review latest',lambda:self.preview(history[0]) if history else self.set_message('Create an export first.'))),
            Label('CONNECTION\n'+safe_text(self.settings.url)+'\nSource: '+self.settings.source_mode,style='class:muted'),
            Label('FILES STAY HERE\n'+safe_text(self.store.exports),style='class:muted')]
        self.show('overview','Your Home Assistant context','A reusable snapshot, not a live AI connection.',rows,self.controls['export'])

    def export_page(self):
        if not self.settings:self.connection();return
        start=self.button('Create snapshot',lambda:self.schedule(self.export_async()),name='run-export')
        rows=[Label('Full context: TXT + ZIP',style='class:title'),
              Label('Includes enabled and disabled entity registry entries, live readings,\nphone registrations, action descriptions and readable configuration.\nPartial data is labeled. Expected exclusions are not counted as failures.'),
              Frame(Label('1  Read Home Assistant\n2  Mask sensitive values\n3  Write a matching TXT and ZIP\n4  Show coverage and review options'),title='This export'),
              Label(f'Keep: {self.settings.retention or "all"} snapshots. Older owned snapshots are removed after a successful write.',style='class:muted'),start]
        self.show('export','Create a snapshot','No automations, scripts, notifications or lights will be triggered.',rows,start)

    async def ensure_docker_auth(self):
        if not self.settings or not self.settings.docker_sudo:return
        proc=await asyncio.to_thread(subprocess.run,['sudo','-n','true'],capture_output=True,check=False)
        if proc.returncode:
            result=await run_in_terminal(lambda:subprocess.run(['sudo','-v'],check=False).returncode)
            if result:raise ValueError('Docker authorization was declined.')

    async def export_async(self):
        try:
            await self.ensure_docker_auth()
            self.show('progress','Collecting your context','Everything stays on this machine.',[
                Label('Reading configuration and capabilities. This never executes device actions.'),
                self.text_view('Starting…',height=12,name='progress-log',search=False),
                self.button('Cancel export',self.cancel_job,name='cancel')],self.controls.get('cancel'))
            self.busy=True
            env={**os.environ,'PYTHONPATH':os.pathsep.join([str(self.store.root/'app'),str(self.store.root/'.vendor')]),'PYTHONDONTWRITEBYTECODE':'1'}
            self.process=await asyncio.create_subprocess_exec(sys.executable,'-m','hacontext','--worker',str(self.store.root),
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env,start_new_session=True)
            self.job=self.process;last=None
            while True:
                line=await self.process.stdout.readline()
                if not line:break
                try:message=json.loads(line)
                except ValueError:continue
                if message.get('type')=='progress':
                    viewer=self.controls.get('progress-log')
                    if viewer:viewer.text=viewer.text+'\n'+safe_text(message['message'])
                    self.set_message(message['message'])
                else:last=message
            code=await self.process.wait()
            self.busy=False;self.process=None;self.job=None
            if code<0:self.export_page();self.set_message('Export canceled. No Home Assistant data was changed.');return
            if not last or last.get('type')!='done':
                raise ValueError(last.get('message','Export stopped unexpectedly. No successful snapshot was reported.') if last else 'Export stopped unexpectedly.')
            path=Path(last['path'])
            if path not in self.store.history():raise ValueError('Export completed but the snapshot identity could not be verified.')
            self.export_done(path,last['summary'])
        except Exception as exc:
            self.busy=False;self.process=None;self.job=None;self.set_message(safe_error(exc))

    def cancel_job(self):
        if self.process and self.process.returncode is None:
            os.killpg(self.process.pid,signal.SIGTERM)
            self.set_message('Canceling the export worker...')

    def export_done(self,path,summary):
        rows=[Label(summary.get('status','Unknown')+' · '+summary.get('scope',''),style='class:title'),
            Label('Share the TXT with a chat. ZIP contains the same sections.\nReview private details and coverage first.'),
            self.text_view(str(path/'ha-context.txt')+'\n\n'+str(path/'ha-context.zip'),height=5,search=False),
            self.row(self.button('Review files',lambda:self.preview(path)),self.button('View coverage',lambda:self.preview(path,'coverage.json'))),
            self.row(self.button('View issues',lambda:self.preview(path,'issues.json')),self.button('Phone sensors',lambda:self.inventory(True))),
            Label('HA OS: use the Files tab above this terminal to download.\nSSH: the files are on the server; use your SSH client’s file browser.',style='class:muted')]
        self.show('done','Snapshot written',f"{summary.get('warning_count',0)} distinct issue(s). Review before sharing.",rows)

    def history(self):
        history=self.store.history()
        if not history:self.overview();self.set_message('No exports yet.');return
        labels=[]
        for p in history:
            try:s=json.loads((p/'summary.json').read_text());status=s.get('status','Unknown')
            except (OSError,ValueError):status='Unreadable'
            labels.append((str(p),p.name+' · '+status))
        pick=self.select('history',labels,labels[0][0])
        def selected():return Path(pick.current_value)
        self.show('history','Export history','Only identified ha-context snapshots are listed.',[
            Box(pick,height=Dimension(min=3,max=12),padding=0),
            self.row(self.button('Review',lambda:self.preview(selected())),self.button('Compare',lambda:self.compare(selected()))),
            self.row(self.button('Delete selected',lambda:self.confirm('Delete this snapshot?',str(selected()),'DELETE',lambda:self.delete_selected(selected()))),
                     self.button('Create new',self.export_page))],pick)

    def delete_selected(self,path):self.store.delete_export(path);self.history()

    def compare(self,path):
        others=[p for p in self.store.history() if p!=path]
        if not others:self.set_message('A comparison needs two snapshots.');return
        other=others[0]
        a=json.loads((path/'entities.json').read_text());b=json.loads((other/'entities.json').read_text())
        result=compare_exports(a,b)
        def hashes(p):return {r['path']:r['sha256'] for r in json.loads((p/'manifest.json').read_text())['files'] if r['path'].startswith('config/')}
        ha,hb=hashes(path),hashes(other)
        result['configuration_files_changed']=sorted(k for k in ha.keys()|hb.keys() if ha.get(k)!=hb.get(k))
        self.show('compare','What changed?','From '+path.name+' to '+other.name,[
            Label('Entity comparison ignores transient sensor readings.'),
            self.text_view(json.dumps(result,indent=2,ensure_ascii=False)),self.button('Back',self.history)],scroll=False)

    def preview(self,path,section='summary.json'):
        manifest=json.loads((path/'manifest.json').read_text())
        names=['ha-context.txt','manifest.json']+[r['path'] for r in manifest['files']]
        pick=self.select('sections',[(n,n) for n in names],section if section in names else names[0])
        def open_section():
            name=pick.current_value;target=path/name
            if target.is_symlink() or not target.resolve().is_relative_to(path.resolve()):raise ValueError('Unsafe preview path.')
            with target.open() as f:text=f.read(400000)
            if target.stat().st_size>400000:text+='\n\n[Preview limited to 400,000 characters; the export file is not truncated.]'
            self.controls['preview-text'].text=safe_text(text)
        area=self.text_view('',name='preview-text')
        self.show('preview','Review before sharing',str(path),[
            VSplit([Frame(pick,title='Sections',width=30),area],padding=1),
            self.row(self.button('Open section',open_section),self.button('Back',self.history))],pick,scroll=False)
        open_section()

    def inventory(self,phones=False):
        history=self.store.history()
        if not history:self.overview();self.set_message('Create a snapshot to browse devices.');return
        path=history[0];all_rows=json.loads((path/'entities.json').read_text())
        self.inventory_rows=all_rows
        search=self.field('inventory-search','Search entity ID, name, device, area or platform','')
        phone=self.check('phones-only','Companion App only',phones)
        status=self.select('entity-status',[('all','All entries'),('enabled','Enabled'),('disabled','Disabled'),('unavailable','Unavailable')],'all')
        table=self.select('entities',[('','Press Apply filters')],'')
        self.controls['inventory-table']=table
        details=self.text_view('',height=8,name='entity-details',search=False)
        def apply_filter():
            q=self.controls['inventory-search'].text.casefold()
            state=self.controls['entity-status'].current_value
            ph=self.controls['phones-only'].checked
            rows=[]
            for r in all_rows:
                disabled=bool(r.get('disabled_by'))
                if ph and r.get('platform')!='mobile_app':continue
                if state=='enabled' and disabled:continue
                if state=='disabled' and not disabled:continue
                if state=='unavailable' and r.get('state')!='unavailable':continue
                if q and q not in json.dumps(r,ensure_ascii=False).casefold():continue
                rows.append(r)
            self.filtered_entities=rows
            table.values=[(r['entity_id'],safe_text(r['entity_id']+'  ·  '+('DISABLED' if r.get('disabled_by') else str(r.get('state','unknown'))))) for r in rows] or [('', 'No matching entities')]
            table.current_value=table.values[0][0];table._selected_index=0
            self.set_message(f'{len(rows)} matches from {path.name}. These are snapshot readings, not live readings.')
        def show_entity():
            row=next((r for r in all_rows if r['entity_id']==table.current_value),None)
            self.controls['entity-details'].text=safe_text(json.dumps(row,indent=2,ensure_ascii=False)) if row else 'No selection.'
        def save_selection():
            rows=getattr(self,'filtered_entities',[])
            out=self.store.local/'selections'/'selected-entities.txt'
            private_replace(out,'SELECTED ENTITY VIEW — not a full HA configuration.\nSource snapshot: '+path.name+'\n\n'+json.dumps(rows,ensure_ascii=False,indent=2))
            self.set_message('Saved filtered view: '+str(out))
        self.show('inventory','Devices & sensors','Correct IDs, registry status and Companion App registrations.',[
            search,self.row(phone,self.button('Apply filters',apply_filter)),
            Box(status,height=4,padding=0),Box(table,height=Dimension(min=3,max=10),padding=0),
            self.row(self.button('Show details',show_entity),self.button('Save filtered view',save_selection)),details,
            self.button('Phone registrations',lambda:self.preview(path,'companion.json'))],self.controls['inventory-search'])
        apply_filter()

    def diagnostics_page(self):
        if not self.settings:self.connection();return
        start=self.button('Run checks',lambda:self.schedule(self.run_checks()),name='checks')
        self.show('diagnostics','Connection diagnostics','Separate tests; no action or notification is sent.',[
            Label('REST API   /   WebSocket registry   /   Configuration file access'),
            self.text_view(json.dumps(self.checks,indent=2) if self.checks else 'No checks in this session.',height=13,name='check-output'),
            self.row(start,self.button('Connection settings',self.connection))],start)

    async def run_checks(self):
        try:
            await self.ensure_docker_auth();self.busy=True;self.set_message('Testing selected source...')
            result=await asyncio.to_thread(diagnostics,self.settings,self.store.token())
            self.checks=result
            self.controls['check-output'].text=safe_text(json.dumps(result,indent=2,ensure_ascii=False))
            private_replace(self.store.logs/'last-check.json',json.dumps(result,indent=2))
            self.set_message('Checks finished. FAILED means missing data, not a broken physical device.')
        except Exception as exc:self.set_message(safe_error(exc))
        finally:self.busy=False

    def notes_page(self):
        editor=self.field('notes-editor','Physical context, intent and external applications',self.store.notes.read_text() if self.store.notes.exists() else '',height=13)
        def save():private_replace(self.store.notes,self.controls['notes-editor'].text);self.set_message('Notes saved. They will be included in the next export.')
        self.show('notes','Notes for future chats','Never put credentials here. Notes are included as user-provided context.',[
            editor,self.button('Save notes',save)],self.controls['notes-editor'])

    def docs(self):
        docs=self.store.root/'app/docs'
        files=sorted(docs.glob('*.md'))
        if not files:self.set_message('Documentation files are missing from this installation.');return
        pick=self.select('docs',[(str(p),p.stem.replace('-',' ').title()) for p in files],str(files[0]))
        viewer=self.text_view(files[0].read_text(),name='doc-text')
        def open_doc():self.controls['doc-text'].text=safe_text(Path(pick.current_value).read_text())
        self.show('docs','Documentation','Included with the app. Use Ctrl-F inside the text to search.',[
            VSplit([Frame(pick,title='Chapters',width=25),viewer],padding=1),
            self.row(self.button('Open chapter',open_doc),self.button('Back',self.overview if self.settings else self.welcome))],pick,scroll=False)

    def settings_page(self):
        if not self.settings:self.welcome();return
        settings=dataclasses.asdict(self.settings)
        self.show('settings','Settings','Credentials are never displayed here.',[
            self.text_view(json.dumps(settings,indent=2,ensure_ascii=False),height=13),
            self.row(self.button('Edit settings',self.connection),self.button('Privacy & retention',self.privacy_page)),
            self.row(self.button('Repair command',lambda:self.schedule(self.install_command())),self.button('Maintenance',self.maintenance))])

    def confirm(self,title,details,word,action:Callable):
        entry=self.field('confirm-word','Type '+word+' to confirm','')
        def confirm_action():
            if self.controls['confirm-word'].text!=word:raise ValueError('Confirmation does not match. Nothing changed.')
            action()
        self.show('confirm',title,details,[entry,
            self.row(self.button('Confirm',confirm_action,name='confirm'),self.button('Cancel',self.maintenance))],self.controls['confirm-word'])

    def reset_confirm(self):
        def reset():
            self.store.reset();self.settings=None;self.pending=Settings();self.pending_token=''
            if self.store.addon:self.pending=Settings(url='http://supervisor',source_mode='local',source_dir='/homeassistant_config',supervisor=True)
            self.welcome();self.set_message('Settings reset. Exports and notes were kept.')
        self.confirm('Reset connection and preferences?','The token is removed locally. Exports, notes and Home Assistant stay untouched.','RESET',reset)

    def maintenance(self):
        rows=[]
        if self.store.config.exists():rows.append(self.button('Reset settings',self.reset_confirm,name='reset'))
        legacy=legacy_candidates(Path.home(),self.store.root) if not self.store.addon else []
        if legacy:rows.append(self.button(f'Review old files ({len(legacy)})',self.legacy_page,name='legacy'))
        if self.store.addon:
            rows+=[Label('HA OS owns this app installation.\nTo remove its image and private data, use:\nSettings → Apps → ha-context → Uninstall.\n\nThe Home Assistant configuration mount is read-only.'),
                   self.button('Open removal guide',self.docs)]
        else:
            rows+=[self.button('Create shareable source',self.share_source),
                   self.button('Update from Git',self.update_page),
                   self.button('Install source ZIP',self.package_update),
                   self.button('Uninstall ha-context',self.uninstall_confirm,name='uninstall')]
        rows.append(Label('Maintenance never resets Home Assistant, Companion App or other applications.',style='class:muted'))
        self.show('maintenance','Maintenance','Explicit actions, with a preview before removal.',rows)

    def legacy_page(self):
        paths=legacy_candidates(Path.home(),self.store.root)
        if not paths:self.maintenance();return
        pick=self.select('legacy-paths',[(str(p),safe_text(p)) for p in paths],str(paths[0]))
        def selected():
            path=Path(pick.current_value)
            def remove():remove_legacy(path,Path.home(),self.store.root);self.legacy_page() if legacy_candidates(Path.home(),self.store.root) else self.welcome() if not self.settings else self.maintenance()
            self.confirm('Remove recognized old exporter files?',str(path)+'\nOnly this selected old exporter path is removed.','REMOVE',remove)
        self.show('legacy','Previous exporter files detected','Only positively identified old files are offered. Nothing is removed automatically.',[
            pick,self.button('Remove selected',selected),self.button('Back',self.maintenance)],pick)

    def uninstall_confirm(self):
        self.confirm('Uninstall ha-context?',str(self.store.root)+'\nRemoves program, token, notes, exports and its command shortcut.\nHome Assistant itself is never removed.','UNINSTALL',lambda:self.schedule(self.uninstall_async()))

    async def uninstall_async(self):
        try:
            from .maintenance import remove_system_link
            link=Path('/usr/local/bin/ha-context')
            if link.is_symlink() and link.resolve()==(self.store.root/'ha-context').resolve() and not os.access(link.parent,os.W_OK):
                result=await run_in_terminal(lambda:subprocess.run(['sudo','-v'],check=False).returncode)
                if result:raise ValueError('Authorization declined. Installation remains.')
                await asyncio.to_thread(remove_system_link,self.store)
            self.store.uninstall();self.uninstall_requested=True;self.app.exit()
        except Exception as exc:self.set_message(safe_error(exc))

    def share_source(self):
        out=source_archive(self.store.root,self.store.local/'sharing'/'ha-context-source.zip')
        self.set_message('Clean source package: '+str(out)+' — excludes tokens, exports and private settings.')

    def update_page(self):
        if not (self.store.root/'.git').is_dir():
            self.show('update','Update this installation','This copy was installed from a package, not a Git clone.',[
                Label('Choose Install source ZIP for a newer trusted source package.\nYour local settings, token, notes and exports are preserved.'),
                self.button('Install source ZIP',self.package_update),self.button('Back',self.maintenance)]);return
        self.confirm('Update from this repository’s origin?','Fetch and fast-forward only. Refuses tracked local changes.\nRestart ha-context afterwards to load the new code.','UPDATE',lambda:self.schedule(self.git_update()))

    async def git_update(self):
        from .maintenance import git_update
        self.busy=True;self.set_message('Checking and updating the existing Git checkout...')
        try:
            result=await asyncio.to_thread(git_update,self.store.root)
            self.restart_page(result)
        except Exception as exc:self.set_message(safe_error(exc))
        finally:self.busy=False

    def package_update(self):
        field=self.field('package-path','Path to a trusted ha-context source ZIP on this machine','')
        def confirm_update():
            path=Path(self.controls['package-path'].text).expanduser()
            self.confirm('Install this source package?',str(path)+'\nOnly program files are replaced; local data is preserved.\nUse packages from a source you trust.','UPDATE',lambda:self.schedule(self.zip_update(path)))
        self.show('package-update','Install a source package','No git commands are needed.',[field,self.button('Review & install',confirm_update),self.button('Back',self.maintenance)],self.controls['package-path'])

    async def zip_update(self,path):
        from .maintenance import install_source_zip
        self.busy=True;self.set_message('Validating package and saving a code rollback copy...')
        try:
            await asyncio.to_thread(install_source_zip,self.store,path)
            self.restart_page('Source updated. Local settings, notes and exports were preserved.')
        except Exception as exc:self.set_message(safe_error(exc))
        finally:self.busy=False

    def restart_page(self,message):
        self.side=HSplit([Label('RESTART REQUIRED'),self.button('Exit',self.quit)])
        self.show('restart','Open ha-context again',message,[
            Label('The code on disk has changed. Restart to load one consistent version.'),
            self.button('Exit',self.quit)])

    async def shutdown(self):
        worker=self.process
        if worker and worker.returncode is None:
            try:os.killpg(worker.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:await asyncio.wait_for(worker.wait(),3)
            except asyncio.TimeoutError:
                try:os.killpg(worker.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                await worker.wait()
        if not self.app.is_done:self.app.exit()

    def quit(self):
        if self.closing:return
        self.closing=True
        if self.process and self.process.returncode is None:
            self.app.create_background_task(self.shutdown())
        elif not self.app.is_done:self.app.exit()

    def run(self):
        def signals():
            loop=asyncio.get_running_loop()
            for sig in (signal.SIGTERM,signal.SIGHUP):
                loop.add_signal_handler(sig,self.quit)
        self.app.run(pre_run=signals)

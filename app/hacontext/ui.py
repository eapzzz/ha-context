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
from .ui_widgets import InstantList, CycleChoice, navigation_button, action_rows, wrap_document
from .state import (Store, Settings, safe_text, safe_error, discover_containers, choose_endpoint,
                    diagnostics, legacy_candidates, remove_legacy, compare_exports, private_replace,
                    source_archive)

STYLE=Style.from_dict({
    '':'bg:#13212d #dce7f0', 'brand':'bg:#13212d #dfb983 bold',
    'header':'bg:#13212d #85b9d4', 'frame.border':'#354a5a', 'frame.label':'#a4c9dc bold',
    'sidebar':'bg:#111d28 #9bb0bf', 'body':'bg:#172734 #dce7f0',
    'label':'#dce7f0', 'muted':'#93a9ba', 'title':'#dce7f0 bold',
    'button':'bg:#253e50 #c9e0ed', 'button.focused':'bg:#9acbe2 #11212d bold',
    'button.arrow':'#95bacf', 'text-area':'bg:#142330 #dce7f0',
    'text-area focused':'bg:#1c3242', 'radio-list':'bg:#172734',
    'radio-selected':'bg:#29495d #e2eff6 bold', 'radio-checked':'#e1bb83',
    'checkbox':'#e1bb83', 'checkbox-selected':'#9acbe2 bold',
    'status':'bg:#203646 #dcc39e', 'footer':'bg:#111d28 #9bb0bf',
    'nav':'bg:#111d28 #9bb0bf','nav.active':'bg:#213a4c #dfb983 bold',
    'nav.focused':'bg:#314f63 #eef5fa bold',
    'search-toolbar':'bg:#29495d #ffffff', 'scrollbar.background':'bg:#213747',
    'scrollbar.button':'bg:#63879d',
})


class ContextUI:
    def __init__(self, store: Store, *, input=None, output=None):
        self.store=store
        self.controls={}
        self.nav_buttons=[];self.page_focus=None;self.save_action=None
        self.note_drafts={};self.inventory_filter=('', 'all', False)
        self._snapshot_cache={}
        self.page=''; self.heading='';self.subtitle=''
        self.message='';self.busy=False;self.process=None
        self.detected=[];self.pending=Settings();self.pending_token='';self.checks=[]
        self.uninstall_requested=False; self.closing=False; self.exit_pending=False
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
        @bindings.add('f6')
        def switch_pane(event):self.focus_navigation()
        @bindings.add('escape', eager=True)
        def escape(event):
            if event.app.layout.is_searching:
                from prompt_toolkit.search import stop_search
                stop_search();return
            if self.page=='confirm' and getattr(self,'cancel_action',None):self.cancel_action()
            elif self.page=='annotation' and getattr(self,'annotation_back',None):self.annotation_back()
            else:self.focus_navigation()
        @bindings.add('c-s')
        def save_current(event):
            if self.save_action and not self.busy:self.save_action()
        @bindings.add('c-f')
        def search_current(event):
            from prompt_toolkit.search import start_search
            control=event.app.layout.current_control
            name={'docs':'doc-text','preview':'preview-text'}.get(self.page)
            if name and name in self.controls:
                area=self.controls[name];event.app.layout.focus(area);control=area.control
            if hasattr(control,'search_buffer_control') and control.search_buffer_control:
                start_search(control)
        self.workspace=VSplit([
            Box(DynamicContainer(lambda:self.side),padding_left=1,padding_right=1,
                padding_top=1,padding_bottom=0,width=Dimension.exact(24),style='class:sidebar'),
            Window(width=1,char='│',style='class:frame.border'),
            Box(HSplit([
                Window(FormattedTextControl(lambda:[('class:title',self.heading)]),height=1),
                Window(FormattedTextControl(lambda:safe_text(self.subtitle)),height=2,wrap_lines=True,style='class:muted'),
                DynamicContainer(lambda:self.body),
            ],style='class:body'),padding_left=2,padding_right=2,padding_top=1,
               padding_bottom=1,style='class:body')
        ],height=lambda:Dimension.exact(max(1,self.app.output.get_size().rows-4)),style='class:body')
        root=HSplit([
            Window(FormattedTextControl(lambda:[('class:brand','  ha-context'),
                ('class:header','  /  HOME ASSISTANT CONTEXT'),('class:muted','  '+__version__)]),height=1),
            Window(FormattedTextControl(lambda:'  '+safe_text(self.pending.label)+'  ·  LOCAL / READ ONLY'),height=1,style='class:muted'),
            self.workspace,
            Window(FormattedTextControl(lambda:safe_text(' '+(str(len(self.note_drafts))+' unsaved note(s) · ' if self.note_drafts else '')+self.message)),height=1,style='class:status'),
            Window(FormattedTextControl(' F6 Menu  Tab Next  Esc Back/Menu  Ctrl-S Save  F1 Help  Ctrl-Q Quit'),height=1,style='class:footer'),
        ])
        self.app=Application(layout=Layout(root),key_bindings=bindings,style=STYLE,
            full_screen=True,mouse_support=True,input=input,output=output)
        self.app.ttimeoutlen=.04
        self.doc_resize=None
        self.app.before_render+=lambda _: self.doc_resize() if self.page=='docs' and self.doc_resize else None
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
        button=Button(text=text,handler=guarded,width=max(10,min(30,len(text)+2)),left_symbol=' ',right_symbol=' ')
        if name:self.controls[name]=button
        return button

    def row(self,*buttons):
        return action_rows(buttons,lambda:max(20,self.app.output.get_size().columns-29))

    def field(self,name,label,value='',*,password=False,height=1):
        area=TextArea(text=str(value),multiline=height>1,password=password,height=height,focus_on_click=True,
                      scrollbar=height>1,wrap_lines=height>1,name=name)
        self.controls[name]=area
        return HSplit([Label(label,style='class:muted'),area],padding=0)

    def select(self,name,values,default=None,on_change=None):
        value=InstantList(values,default=default,on_change=on_change)
        self.controls[name]=value
        return value

    def check(self,name,label,value=False):
        c=Checkbox(label,checked=value);c.show_scrollbar=False;self.controls[name]=c;return c

    def sidebar(self):
        self.nav_buttons=[]
        if self.onboarding:
            widgets=[Label('FIRST RUN',style='class:muted'),Window(height=1)]
            widgets += [Label(t) for t in ['1  Welcome','2  Connection','3  Source','4  Privacy & notes','5  Ready']]
            items=[('Documentation',self.docs,'docs'),('Maintenance',self.maintenance,'maintenance')]
            widgets.append(Window(height=1))
        else:
            widgets=[Label('WORKSPACE',style='class:muted'),Window(height=1)]
            items=[('Overview',self.overview,'overview'),('Create export',self.export_page,'export'),
                ('Devices & sensors',self.inventory,'inventory'),('Export history',self.history,'history'),
                ('Diagnostics',self.diagnostics_page,'diagnostics'),('Notes',self.notes_page,'notes'),
                ('Documentation',self.docs,'docs'),('Settings',self.settings_page,'settings'),
                ('Maintenance',self.maintenance,'maintenance')]
        for label,action,route in items:
            button=self.button(label,action)
            navigation_button(button,lambda r=route:self.active_route()==r,self.move_navigation)
            self.nav_buttons.append((route,button));widgets.append(button)
        widgets += [Window(height=1),Label('F6  Menu / content',style='class:muted'),
                    Label('↑↓  Choose a page',style='class:muted'),Window(height=1),self.button('Exit',self.quit)]
        self.side=ScrollablePane(HSplit(widgets),show_scrollbar=False,max_available_height=40)

    def active_route(self):
        groups={'annotation':'notes','global-notes':'notes','note-target':'notes',
                'preview':'history','compare':'history','done':'export','progress':'export',
                'connection':'settings','source':'settings','privacy':'settings','ready':'settings',
                'legacy':'maintenance','update':'maintenance','confirm':'maintenance','package-update':'maintenance'}
        return groups.get(self.page,self.page)

    def move_navigation(self,delta):
        if not self.nav_buttons:return
        buttons=[b for _,b in self.nav_buttons]
        current=next((i for i,b in enumerate(buttons) if self.app.layout.has_focus(b)),0)
        self.app.layout.focus(buttons[(current+delta)%len(buttons)])

    def focus_navigation(self):
        if not self.nav_buttons:return
        if any(self.app.layout.has_focus(b) for _,b in self.nav_buttons) and self.page_focus:
            try:self.app.layout.focus(self.page_focus);return
            except ValueError:pass
        button=next((b for r,b in self.nav_buttons if r==self.active_route()),self.nav_buttons[0][1])
        self.app.layout.focus(button)

    def snapshot(self):
        history=self.store.history()
        if not history:return None,[]
        path=history[0];file=path/'entities.json'
        stamp=(path,file.stat().st_mtime_ns,file.stat().st_size)
        if self._snapshot_cache.get('stamp')!=stamp:
            self._snapshot_cache={'stamp':stamp,'path':path,'entities':json.loads(file.read_text())}
        return path,self._snapshot_cache['entities']

    def show(self,page,title,subtitle,widgets,focus=None,*,scroll=True):
        self.page=page;self.heading=title;self.subtitle=subtitle;self.save_action=None
        self.body=ScrollablePane(HSplit(widgets+[Window(height=1)],padding=1),max_available_height=250) if scroll else HSplit(widgets,padding=1)
        self.message=''
        try:
            if focus:self.app.layout.focus(focus)
            else:
                from prompt_toolkit.layout import to_container
                from prompt_toolkit.layout.layout import walk
                choices=[w for w in walk(to_container(self.body)) if isinstance(w,Window) and w.content.is_focusable()]
                if choices:self.app.layout.focus(choices[0])
            self.page_focus=self.app.layout.current_window
        except ValueError:pass
        self.app.invalidate()

    def set_message(self,message):
        self.message=safe_text(message);self.app.invalidate()

    def text_view(self,text,height=None,*,name='viewer',search=True,wrap=False):
        toolbar=SearchToolbar() if search else None
        area=TextArea(text=safe_text(text),read_only=True,scrollbar=True,wrap_lines=wrap,
                      search_field=toolbar,height=height,focus_on_click=True)
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
        pick.on_change=lambda _:open_section()
        area=self.text_view('',name='preview-text')
        self.show('preview','Review before sharing',str(path),[
            VSplit([Frame(pick,title='Sections',width=30),area],padding=1),
            self.row(self.button('Open section',open_section),self.button('Back',self.history))],pick,scroll=False)
        open_section()

    def inventory(self,phones=None):
        path,all_rows=self.snapshot()
        if not path:self.overview();self.set_message('Create a snapshot to browse devices.');return
        self.inventory_rows=all_rows
        q,selected_status,previous_phone=self.inventory_filter
        ph=previous_phone if phones is None else phones
        search=self.field('inventory-search','Search IDs, names, rooms or platforms',q)
        phone=self.check('phones-only','Phone only',ph);phone.width=15
        status=CycleChoice([('all','All entries'),('enabled','Enabled'),('disabled','Disabled'),('unavailable','Unavailable')],selected_status)
        self.controls['entity-status']=status
        table=self.select('entities',[('', 'Loading inventory')],'')
        table.current_value=getattr(self,'inventory_selected','')
        self.controls['inventory-table']=table
        details=self.text_view('',name='entity-details',search=False,wrap=True)
        detail_area=self.controls['entity-details']
        by_id={r['entity_id']:r for r in all_rows}
        searchable={r['entity_id']:json.dumps(r,ensure_ascii=False).casefold() for r in all_rows}
        def selected():return by_id.get(table.current_value)
        def show_entity():
            r=selected()
            if not r:detail_area.text='No matching entity.';return
            self.inventory_selected=r['entity_id']
            device=r.get('device_id');area=r.get('effective_area_id') or r.get('area_id')
            text=(r.get('name') or r['entity_id'])+'\n'+r['entity_id']+'\n\n'
            text+='State: '+str(r.get('state','unknown'))+'\nRegistry: '+('Disabled ('+str(r['disabled_by'])+')' if r.get('disabled_by') else 'Enabled')
            text+='\nPlatform: '+str(r.get('platform') or 'Not supplied')+'\nRoom: '+str(r.get('effective_area_name') or area or 'Not assigned')
            text+='\nDevice: '+str(device or 'Not linked')
            for kind,ident in [('entity',r['entity_id']),('device',device),('area',area)]:
                note=self.store.annotation(kind,ident) if ident else ''
                if note:text+='\n\n'+kind.title()+' note (user context):\n'+note
            text+='\n\nAttributes\n'+json.dumps(r.get('attributes',{}),indent=2,ensure_ascii=False)
            detail_area.text=safe_text(text);detail_area.buffer.cursor_position=0
        def apply_filter():
            query=self.controls['inventory-search'].text.casefold()
            state=status.current_value;companion=phone.checked
            self.inventory_filter=(self.controls['inventory-search'].text,state,companion)
            rows=[r for r in all_rows if (not companion or r.get('platform')=='mobile_app')
                  and (state!='enabled' or not r.get('disabled_by'))
                  and (state!='disabled' or r.get('disabled_by'))
                  and (state!='unavailable' or r.get('state')=='unavailable')
                  and (not query or query in searchable[r['entity_id']])]
            self.filtered_entities=rows
            table.replace([(r['entity_id'],safe_text(r['entity_id']+' · '+('disabled' if r.get('disabled_by') else str(r.get('state','unknown'))))) for r in rows])
            show_entity();self.set_message(f'{len(rows)} / {len(all_rows)} entities · snapshot {path.name} · not live')
        def annotate(kind):
            r=selected()
            if not r:self.set_message('Select an entity first.');return
            ident={'entity':r['entity_id'],'device':r.get('device_id'),'area':r.get('effective_area_id') or r.get('area_id')}[kind]
            if not ident:self.set_message('This entity has no '+kind+' link in the snapshot.');return
            self.edit_annotation(kind,ident,self.inventory)
        def save_selection():
            out=self.store.local/'selections'/'selected-entities.txt'
            private_replace(out,'SELECTED ENTITY VIEW — not a full HA configuration.\nSource snapshot: '+path.name+'\n\n'+json.dumps(self.filtered_entities,ensure_ascii=False,indent=2))
            self.set_message('Saved filtered view: '+str(out))
        table.on_change=lambda _:show_entity()
        status.on_change=lambda _:apply_filter()
        toggle=phone._handle_enter
        def on_toggle():toggle();apply_filter()
        phone._handle_enter=on_toggle
        panels=VSplit([Frame(table,title='Entities'),Frame(details,title='Selected entity')],padding=1,height=Dimension(min=4,weight=1))
        self.show('inventory','Devices & sensors','Snapshot data. Select a row to inspect it or attach context.',[
            search,self.row(phone,status,self.button('Apply filters',apply_filter)),panels,
            self.row(self.button('Entity note',lambda:annotate('entity')),self.button('Device note',lambda:annotate('device')),self.button('Room note',lambda:annotate('area'))),
            self.row(self.button('Save filtered view',save_selection),self.button('Phone registrations',lambda:self.preview(path,'companion.json'))),
        ],self.controls['inventory-search'],scroll=False)
        self.controls['inventory-search'].buffer.on_text_changed+=lambda _:apply_filter()
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
        notes=self.store.load_annotations()
        pick=self.select('note-list',[((n['kind'],n['id']),n['kind'].title()+' · '+n['id']) for n in notes] or [('', 'No object notes yet')])
        viewer=self.text_view('',name='note-preview',wrap=True)
        target=self.controls['note-preview']
        def preview():
            key=pick.current_value
            target.text=safe_text(self.store.annotation(*key)) if key else 'Attach a note to an entity, device or room.\n\nGlobal context is separate and remains available in General notes.'
        def edit():
            if not pick.current_value:self.note_target();return
            self.edit_annotation(*pick.current_value,self.notes_page)
        pick.on_change=lambda _:preview()
        general=self.note_drafts.get('general',self.store.notes.read_text() if self.store.notes.exists() else '')
        self.show('notes','Context notes','Included in your next export. They never modify Home Assistant.',[
            Label(f'{len(notes)} object notes  ·  {len(general)} characters of general context',style='class:muted'),
            VSplit([Frame(pick,title='Attached to',width=Dimension(weight=1)),Frame(viewer,title='Note',width=Dimension(weight=1))],padding=1,height=Dimension(min=4,weight=1)),
            self.row(self.button('General notes',self.general_notes),self.button('Add note',self.note_target),self.button('Edit note',edit)),
        ],pick,scroll=False)
        preview()

    def general_notes(self):
        saved=self.store.notes.read_text() if self.store.notes.exists() else ''
        editor=TextArea(text=self.note_drafts.get('general',saved),multiline=True,scrollbar=True,wrap_lines=True,focus_on_click=True)
        self.controls['notes-editor']=editor
        def changed(_):
            if editor.text==saved:self.note_drafts.pop('general',None)
            else:self.note_drafts['general']=editor.text
        editor.buffer.on_text_changed+=changed
        def save():
            nonlocal saved
            private_replace(self.store.notes,editor.text);saved=editor.text;self.note_drafts.pop('general',None)
            self.set_message('General notes saved. Create a new export to include them.')
        self.show('global-notes','General context','For household rules and external applications. Ctrl-S saves.',[
            editor,self.row(self.button('Save notes',save),self.button('Back',self.notes_page))
        ],editor,scroll=False)
        self.save_action=save

    def note_target(self):
        path,rows=self.snapshot()
        if not path:self.set_message('Create an export first so targets come from actual IDs.');return
        candidates={'entity':[(r['entity_id'],(r.get('name') or r['entity_id'])+' · '+r['entity_id']) for r in rows], 'device':[], 'area':[]}
        for kind,name in [('device','device'),('area','area')]:
            f=path/'registries'/f'{name}.json'
            records=json.loads(f.read_text()) if f.exists() else []
            for r in records:
                ident=r.get('area_id',r.get('id')) if kind=='area' else r.get('id')
                if ident:candidates[kind].append((ident,str(r.get('name_by_user') or r.get('name') or ident)+' · '+ident))
        kind=self.select('note-kind',[('entity','Entity / sensor'),('device','Device'),('area','Room / area')],'entity')
        search=self.field('note-search','Find a target','')
        choices=self.select('note-target',[('', 'Select a target')])
        def filter_():
            q=self.controls['note-search'].text.casefold()
            choices.replace([(ident,safe_text(label)) for ident,label in candidates[kind.current_value] if q in label.casefold()])
        def edit():
            if choices.current_value:self.edit_annotation(kind.current_value,choices.current_value,self.notes_page)
            else:self.set_message('No matching target in this snapshot.')
        kind.on_change=lambda _:filter_()
        self.show('note-target','Attach context','Only real IDs from the latest snapshot are offered.',[
            Box(kind,height=3,padding=0),search,Frame(choices,title='Targets'),
            self.row(self.button('Write note',edit),self.button('Back',self.notes_page))
        ],self.controls['note-search'],scroll=False)
        self.controls['note-search'].buffer.on_text_changed+=lambda _:filter_()
        filter_()

    def edit_annotation(self,kind,ident,back=None):
        self.annotation_back=back or self.notes_page
        key=(kind,ident)
        editor=TextArea(text=self.note_drafts.get(key,self.store.annotation(kind,ident)),
                        multiline=True,scrollbar=True,wrap_lines=True,focus_on_click=True)
        self.controls['annotation-editor']=editor
        editor.buffer.on_text_changed+=lambda _:self.note_drafts.__setitem__(key,editor.text)
        def save():
            self.store.save_annotation(kind,ident,editor.text);self.note_drafts.pop(key,None)
            self.annotation_back();self.set_message('Note saved. Create a new export to include it.')
        def delete():
            self.confirm('Delete this context note?',ident,'DELETE',lambda:remove())
        def remove():
            self.store.save_annotation(kind,ident,'');self.note_drafts.pop(key,None);self.annotation_back()
        self.show('annotation',kind.title()+' note',ident,[
            Label('Describe placement, purpose or constraints. No passwords or tokens.',style='class:muted'),
            editor,self.row(self.button('Save note',save),self.button('Delete note',delete),self.button('Back',self.annotation_back))
        ],editor,scroll=False)
        self.save_action=save

    def docs(self):
        files=sorted((self.store.root/'app/docs').glob('*.md'))
        if not files:self.set_message('Documentation files are missing from this installation.');return
        contents={str(p):p.read_text(encoding='utf-8') for p in files}
        short={'01':'Start here','02':'Connection','03':'Exports','04':'Phone sensors','05':'Privacy','06':'Maintenance','07':'Export or MCP','08':'Navigation','09':'Context notes'}
        labels=[(str(p),short.get(p.stem[:2],p.stem.replace('-',' '))) for p in files]
        pick=self.select('docs',labels,getattr(self,'doc_selected',str(files[0])))
        viewer=self.text_view('',name='doc-text',wrap=True)
        area=self.controls['doc-text']
        rendering={'width':None,'chapter':None}
        def render_doc():
            width=max(18,self.app.output.get_size().columns-52)
            if rendering['width']==width and rendering['chapter']==pick.current_value:return
            old_position=area.buffer.cursor_position if rendering['chapter']==pick.current_value else 0
            area.text=safe_text(wrap_document(contents[pick.current_value],width))
            area.buffer.cursor_position=min(old_position,len(area.text))
            rendering.update(width=width,chapter=pick.current_value)
        self.doc_resize=render_doc
        def open_doc():
            self.doc_selected=pick.current_value
            render_doc();area.buffer.cursor_position=0
            self.set_message(f'Chapter {pick._selected_index+1} / {len(files)} · ↑↓ or click a chapter · Ctrl-F searches the text')
        pick.on_change=lambda _:open_doc()
        chapters=Frame(pick,title='Chapters',width=Dimension.exact(21))
        self.show('docs','Documentation','Offline guide. Selecting a chapter opens it immediately.',[
            VSplit([chapters,viewer],padding=1,height=Dimension(min=4,weight=1)),
            self.row(self.button('Previous',lambda:pick.move(-1)),self.button('Next',lambda:pick.move(1)),self.button('Back',self.overview if self.settings else self.welcome))
        ],pick,scroll=False)
        open_doc()

    def settings_page(self):
        if not self.settings:self.welcome();return
        cfg=self.settings
        source={'api':'API only','local':'Local configuration folder','container':cfg.runtime.title()+' container'}.get(cfg.source_mode,cfg.source_mode)
        location=cfg.container if cfg.source_mode=='container' else cfg.source_dir if cfg.source_mode=='local' else 'No configuration files selected'
        self.show('settings','Settings','Private credentials stay in this installation.',[
            Frame(Label(safe_text(cfg.url)+'\n'+source+'\n'+safe_text(location)),title='Connection & source'),
            Frame(Label(f'Keep {cfg.retention or "all"} snapshots  ·  Timeout {cfg.timeout}s\nDevice capabilities: '+('included' if cfg.device_details else 'not selected')+'\nNetwork identifiers: '+('masked' if cfg.network_privacy else 'retained for context')),title='Export preferences'),
            self.row(self.button('Edit settings',self.connection),self.button('Privacy & retention',self.privacy_page)),
            self.row(self.button('Repair command',lambda:self.schedule(self.install_command())),self.button('Maintenance',self.maintenance))])

    def confirm(self,title,details,word,action:Callable):
        saved=(self.page,self.heading,self.subtitle,self.body,self.controls.copy(),self.page_focus,self.save_action)
        def cancel():
            self.page,self.heading,self.subtitle,self.body,self.controls,self.page_focus,self.save_action=saved
            self.cancel_action=None;self.exit_pending=False
            if self.page_focus:
                try:self.app.layout.focus(self.page_focus)
                except ValueError:pass
            self.app.invalidate()
        self.cancel_action=cancel
        entry=self.field('confirm-word','Type '+word+' to confirm','')
        field=self.controls['confirm-word']
        def confirm_action():
            if field.text!=word:raise ValueError('Confirmation does not match. Nothing changed.')
            action()
        self.show('confirm',title,details,[entry,
            self.row(self.button('Confirm',confirm_action,name='confirm'),self.button('Cancel',cancel))],field)

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
        if self.note_drafts:
            if not self.exit_pending:
                self.exit_pending=True
                self.confirm('Unsaved context notes',
                    'Cancel and save your notes with Ctrl-S, or type DISCARD to quit without saving drafts.',
                    'DISCARD',self._quit_now)
            return
        self._quit_now()

    def _quit_now(self):
        if self.closing:return
        self.closing=True
        if self.process and self.process.returncode is None:
            self.app.create_background_task(self.shutdown())
        elif not self.app.is_done:self.app.exit()

    def run(self):
        def signals():
            loop=asyncio.get_running_loop()
            for sig in (signal.SIGTERM,signal.SIGHUP):
                loop.add_signal_handler(sig,self._quit_now)
        self.app.run(pre_run=signals)

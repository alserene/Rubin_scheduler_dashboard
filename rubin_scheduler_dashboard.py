import param
import pandas as pd
import panel as pn
import bokeh
import logging
import os

from astropy.time import Time
from zoneinfo import ZoneInfo

import schedview
import schedview.compute.scheduler
import schedview.compute.survey
import schedview.collect.scheduler_pickle

"""
Notes
-----
    
- Syntax, naming conventions, formatting, etc., mostly follows Eric's prenight.py.

- Still to implement:
    
    - Survey/basis function holoviz map.
    - Link basis_function selection and map selection to plot display.
    - Link nside drop down selection to map nside.
    - Link color palette drop down selection to map color palette.
    - Beautification of elements (fonts, etc.).
    - Restricting the number of rows displayed for the survey rewards table.
    - Set relative widths of two main columns (perhaps 3/5,2/5?).
    - ...

- Current issues:
    
    - I haven't found a way to display the map. I think we might need a custom panel.
    - Survey rewards table includes hyperlinks for surveys without links.
        - I haven't found a way to fix this with tabulator_formatter options.
    - The Rubin logo isn't right-justified.
    - I haven't found a way to change the title/headings fonts.
        - The styles 'font-family': 'Helvetica' option doesn't do anything.
    - The error log is very unsightly. Is there any way to display this better?
    - The clear_caches function copied from prenight.py doesn't work.
        - sched_app has no attribute stop(). What should go here isntead?
    - The two main columns are given equal width on the page. How to customise this?
    - Basis function table (and a fair few other functions) updates when it shouldn't.
        - listed_survey is not None?
    - When choosing a new survey, the plot title flashes 'Map reward' breifly before clearing.
    - ...

- Pending questions:
    
    - Are users choosing a date or a datetime?
    - Is a 'reward' map always available? If not, when not? When survey reward is infeasible?
        - In sched_maps, some surveys (e.g. tier 3, surveys 1,2) don't have a reward map,
          but in my pickle file, all surveys have reward maps.
    - Should it be 'survey reward table' or 'survey rewards table'?
    - Is the key static (can be an image) or variable?
    - Will all surveys/basis functions have a URL link?
    - Is it okay to not show 'tier' column in survey rewards table?
    - The dashboard defaults to showing survey 0 and basis function 0. How should this be handled?
        - When a new tier/survey is selected, do we continue to display old plot, or remove plot?
            - If continue, plot title will need to show which survey the basis function/map belongs to.
        - When a survey is chosen, should a basis function or a map be automatically loaded for the plot or neither?
    - What resolution colour schemes? 11? 20? 256?
    - ...
"""

DEFAULT_TIMEZONE        = "Chile/Continental"
DEFAULT_CURRENT_TIME    = Time.now()
DEFAULT_SCHEDULER_FNAME = "scheduler.pickle.xz"

color_palettes = [s for s in bokeh.palettes.__palettes__ if "256" in s]

LOGO      = "/Users/me/Documents/2023/ADACS/Panel_scheduler/lsst_white_logo.png"
key_image = "/Users/me/Documents/2023/ADACS/Panel_scheduler/key_image.png"
map_image = "/Users/me/Documents/2023/ADACS/Panel_scheduler/map_image.png"     # Temporary, until map can be displayed.

pn.extension("tabulator",
             css_files   = [pn.io.resources.CSS_URLS["font-awesome"]],
             sizing_mode = "stretch_width",)

#pn.widgets.Tabulator.theme = 'site'

pn.config.console_output = "disable"                                           # To avoid clutter.

logging.basicConfig(format = "%(asctime)s %(message)s",
                    level  = logging.INFO)

debug_info = pn.widgets.Debugger(name        = "Debugger information.",
                                 level       = logging.DEBUG,
                                 sizing_mode = "stretch_both")

class Scheduler(param.Parameterized):
    
    scheduler_fname = param.String(DEFAULT_SCHEDULER_FNAME)
    date            = param.Date(DEFAULT_CURRENT_TIME.datetime.date())
    tier            = param.ObjectSelector(default="", objects=[""])
    survey          = param.Integer(default=-1)
    basis_function  = param.Integer(default=-1)
    survey_map      = param.ObjectSelector(default="", objects=[""])
    nside           = param.ObjectSelector(default="16", objects=["8","16","32"])
    color_palette   = param.ObjectSelector(default="Magma256", objects=color_palettes)
    plot_display    = param.Integer(default=1)

    _scheduler                = param.Parameter(None)
    _conditions               = param.Parameter(None)
    _date_time                = param.Parameter(None)
    _rewards                  = param.Parameter(None)
    _survey_rewards           = param.Parameter(None)
    _listed_survey            = param.Parameter(None)
    _tier_survey_rewards      = param.Parameter(None)
    _basis_functions          = param.Parameter(None)
    _survey_df_widget         = param.Parameter(None)
    _basis_function_df_widget = param.Parameter(None)
    
    
    # Dashboard headings ------------------------------------------------------# Should these functions be below others?
    
    # Panel for dashboard title.
    @param.depends("tier", "survey", "survey_map", "basis_function")
    def dashboard_title(self):
        titleT  = ''; titleS  = ''; titleBF = ''; titleM = ''
        if self._scheduler is not None:
            if self.tier != '':
                titleT = '\nTier {}'.format(self.tier[-1])
                if self.survey >= 0:
                    titleS = ' | Survey {}'.format(self.survey)
                    if self.plot_display == 1:
                        titleM = ' | Map {}'.format(self.survey_map)
                    elif self.plot_display == 2 and self.basis_function >= 0:
                        titleBF = ' | Basis function {}'.format(self.basis_function)
        title_string = 'Scheduler Dashboard' + titleT + titleS + titleBF + titleM
        dashboard_title = pn.pane.Str(title_string,styles={'font-size':'16pt',
                                                           'color':'white',
                                                           'font-weight':'bold',
                                                           #'font-family': 'Helvetica'
                                                            })
        return dashboard_title


    # Panel for survey rewards table title.
    @param.depends("tier")
    def survey_rewards_title(self):
        title_string = ''
        if self._scheduler is not None and self.tier != '':
            title_string = 'Tier {} survey rewards'.format(self.tier[-1])
        survey_rewards_title = pn.pane.Str(title_string, styles={'font-size':'14pt',
                                                                 'color':'white'})
        return survey_rewards_title


    # Panel for basis function table title.
    @param.depends("survey")
    def basis_function_table_title(self):        
        if self._scheduler is not None and self.survey >= 0:
            title_string = 'Basis functions for survey {}'.format(self._tier_survey_rewards.reset_index()['survey_name'][self.survey])
        else:
            title_string = ''
        basis_function_table_title = pn.pane.Str(title_string, styles={'font-size':'14pt',
                                                                       'color':'white'})
        return basis_function_table_title


    # Panel for map title.
    @param.depends("survey", "survey_map", "basis_function")
    def map_title(self):
        if self._scheduler is not None and self.survey >= 0:
            titleA = 'Survey {}\n'.format(self._tier_survey_rewards.reset_index()['survey_name'][self.survey])
            if self.plot_display == 1:
                titleB = 'Map {}'.format(self.survey_map)
            elif self.plot_display == 2 and self.basis_function >= 0:
                titleB = 'Basis function {}: {}'.format(self.basis_function, self._basis_functions['basis_function'][self.basis_function])
            else:
                titleA = ''; titleB = ''
            title_string = titleA + titleB
        else:
            title_string = ''
        map_title = pn.pane.Str(title_string, styles={'font-size':'14pt',
                                                      'color':'white'})
        return map_title

    
    # Widgets and updates -----------------------------------------------------
    
    # Update scheduler if given new pickle file.
    @param.depends("scheduler_fname", watch=True)
    def _update_scheduler(self):
        logging.info("Updating scheduler.")
        try:
            (scheduler, conditions) = schedview.collect.scheduler_pickle.read_scheduler(self.scheduler_fname)
            self._scheduler = scheduler
            self._conditions = conditions
        except Exception as e:
            logging.error(f"Could not load scheduler from {self.scheduler_fname} {e}")
    
    
    # Update datetime if new datetime chosen.
    @param.depends("date", watch=True)
    def _update_date_time(self):
        logging.info("Updating date.")
        self._date_time = Time(pd.Timestamp(self.date, tzinfo=ZoneInfo("Chile/Continental"))).mjd
        logging.info("Date updated to {}".format(self._date_time))
    
    
    # Update survey reward table if given new pickle file or new date.
    @param.depends("_scheduler", "_conditions", "_date_time", watch=True)
    def _update_survey_rewards(self):
        if self._scheduler is None:
            logging.info("No pickle loaded.")
            return
        logging.info("Updating survey rewards.")
        try:
            self._conditions.mjd = self._date_time
            self._scheduler.update_conditions(self._conditions)
            self._rewards        = self._scheduler.make_reward_df(self._conditions)
            survey_rewards = schedview.compute.scheduler.make_scheduler_summary_df(self._scheduler,
                                                                                   self._conditions,
                                                                                   self._rewards)
            self._survey_rewards = survey_rewards
        except Exception as e:
            logging.error(e)
            logging.info("Survey rewards unable to be updated. Perhaps date not in range of pickle data?")
            self._survey_rewards = None
            #self.tier            = "" # can I reset to default?
            #self.survey          = -1
            #self.basis_function  = -1


    # Update available tier selections if given new pickle file.
    @param.depends("_survey_rewards", watch=True)
    def _update_tier_selector(self):
        logging.info("Updating tier selector.")
        if self._survey_rewards is None:
            self.param["tier"].objects = [""]
            self.tier = ""
            return
        tiers = self._survey_rewards.tier.unique().tolist()
        self.param["tier"].objects = tiers
        self.tier = tiers[0]


    # Update (filter) survey list based on tier selection.
    @param.depends("_survey_rewards", "tier", watch=True)
    def _update_survey_reward_table(self):
        if self._survey_rewards is None:
            self._tier_survey_rewards = None
            return
        logging.info("Updating survey rewards for chosen tier.")
        try:
            self._tier_survey_rewards = self._survey_rewards[self._survey_rewards['tier']==self.tier]
        except Exception as e:
            logging.error(e)
            self._tier_survey_rewards = None


    # Widget for survey reward table.
    @param.depends("_tier_survey_rewards")
    def survey_reward_table(self):
        #if self._survey_rewards is None:
        #    self._update_scheduler()
        if self._tier_survey_rewards is None:
            return "No surveys available."
        #logging.info("Updating survey rewards table.")
        tabulator_formatter = {'survey_name': {'type': 'link',
                                                'labelField':'survey_name',
                                                'urlField':'survey_url',
                                                'target':'_blank'}}
        survey_reward_table = pn.widgets.Tabulator(self._tier_survey_rewards[['tier','survey_name','reward','survey_url']],
                                                    #widths={'tier':'10%','survey_name':'50%','reward':'40%'},
                                                    widths={'survey_name':'60%','reward':'40%'},
                                                    sizing_mode='stretch_width',
                                                    show_index=False,
                                                    formatters=tabulator_formatter,
                                                    disabled=True,
                                                    selectable=1,
                                                    hidden_columns=['tier','survey_url'])
        logging.info("Finished updating survey rewards table.")
        self._survey_df_widget = survey_reward_table
        return survey_reward_table


    # Update selected survey based on row selection of survey_reward_table.
    @param.depends("_survey_df_widget.selection", watch=True)
    def update_survey_with_row_selection(self):
        logging.info("Updating survey row selection.")
        try:
            self.survey = self._survey_df_widget.selection[0]
        except Exception as e:
            logging.error(e)
            self.survey = -1                                                   # When no survey selected, survey = -1
    
    
    # Update listed_survey if tier or survey selections change.
    @param.depends("survey", watch=True)
    def _update_listed_survey(self):
        logging.info("Updating listed survey.")
        try:
            tier_id = int(self.tier[-1])
            survey_id = self.survey
            self._listed_survey = self._scheduler.survey_lists[tier_id][survey_id]
        except Exception as e:
            logging.error(e)
            self._listed_survey = None
    

    # Update available map selections if new survey chosen.                    # Add try-catch here?
    @param.depends("_listed_survey", watch=True)
    def _update_map_selector(self):
        if self.tier == "" or self.survey < 0:
            self.param["survey_map"].objects = [""]
            self.survey_map = ""
            return
        logging.info("Updating map selector.")
        self._survey_maps = schedview.compute.survey.compute_maps(self._listed_survey, # Move this into own update function.
                                                                  self._conditions,
                                                                  nside=16)    # Change once nside selector is made.
                                                                  #nside=nside)
        maps = list(self._survey_maps.keys())
        self.param["survey_map"].objects = maps
        if 'reward' in maps:                                                   # If 'reward' map always exists, then this isn't needed.
            self.survey_map = maps[-1]                                         # Reward map usually (always?) listed last.
        else:
            self.survey_map = maps[0]


    # Update the parameter which determines whether a basis function or a map is plotted.
    @param.depends("survey_map", watch=True)
    def _update_plot_display(self):
        self.plot_display = 1                                                  # Display map instead of basis function.


    # Update basis function table if new survey chosen.
    @param.depends("_listed_survey", "survey_reward_table", watch=True)
    def _update_basis_functions(self):
        if self._listed_survey is None:
            return
        logging.info("Updating basis function table.")
        try:
            tier_id = int(self.tier[-1])
            survey_id = self.survey
            #self._listed_survey = self._scheduler.survey_lists[tier_id][survey_id]
            basis_function_df = schedview.compute.survey.make_survey_reward_df(self._listed_survey,
                                                                               self._conditions,
                                                                               self._rewards.loc[[(tier_id, survey_id)], :])
            self._basis_functions = basis_function_df
        except Exception as e:
            logging.error(e)
            self._basis_functions = None


    # Widget for basis function table.
    @param.depends("_basis_functions")
    def basis_function_table(self):
        if self._basis_functions is None:
            #self._update_basis_functions()
            return "No basis functions available."
        logging.info("Creating basis function table.")
        tabulator_formatter = {
            'basis_function': {'type': 'link',
                                'labelField':'basis_function',
                                'urlField':'doc_url',
                                'target':'_blank'}}
        columnns = ['basis_function',
                    'basis_function_class',
                    'feasible',
                    'max_basis_reward',
                    'basis_area',
                    'basis_weight',
                    'max_accum_reward',
                    'accum_area',
                    'doc_url']
        basis_function_table = pn.widgets.Tabulator(self._basis_functions[columnns],
                                                    layout="fit_data",
                                                    show_index=False,
                                                    formatters=tabulator_formatter,
                                                    disabled=True,
                                                    hidden_columns=['doc_url'],
                                                    selectable=1)
        #logging.info("Finished updating basis function table.")
        self._basis_function_df_widget = basis_function_table
        return basis_function_table


    # Update selected basis_function based on row selection of basis_function_table.
    @param.depends("_basis_function_df_widget.selection", watch=True)
    def update_basis_function_with_row_selection(self):
        logging.info("Updating basis function row selection.")
        try:
            self.plot_display = 2                                              # Display basis function instead of a map.
            self.basis_function = self._basis_function_df_widget.selection[0]
        except Exception as e:
            logging.error(e)
            self.basis_function = -1                                           # When no basis function selected, basis_function = -1.



def scheduler_app(date=None, scheduler_pickle=None):
    
    scheduler = Scheduler()
    
    if date is not None:
        scheduler.date = date
    
    if scheduler_pickle is not None:
        scheduler.scheduler_fname = scheduler_pickle
    
    # Dashboard layout.
    sched_app = pn.Column(
        # Title pane across top of dashboard.
        pn.Row(scheduler.dashboard_title,
               pn.layout.HSpacer(),
               pn.pane.PNG(LOGO, height=80),# align='end'),                    # How to right-align image?
               styles={'background':'#048b8c'}),
        pn.Spacer(height=10),
        # Rest of dashboard.
        pn.Row(
            # LHS column (inputs, tables).
            pn.Column(
                # Top-left (inputs, survey table).
                pn.Row(
                    pn.Column(
                        pn.Param(scheduler,
                                 parameters=["scheduler_fname","date","tier"],
                                 #widgets={"date": pn.widgets.DatePicker},
                                 widgets={"date": pn.widgets.DatetimePicker},
                                 name="Select pickle file, date and tier."),
                        ),
                    pn.Column(
                        pn.Row(scheduler.survey_rewards_title,styles={'background':'#048b8c'}),
                        pn.param.ParamMethod(scheduler.survey_reward_table, loading_indicator=True)
                        )
                    ),
                # Bottom-left (basis function table).
                pn.Row(scheduler.basis_function_table_title, styles={'background':'#048b8c'}),
                pn.param.ParamMethod(scheduler.basis_function_table, loading_indicator=True)
                ),
            pn.Spacer(width=10),
            # RHS column (map, key).
            pn.Column(
                # Top-right (map).
                pn.Row(scheduler.map_title,styles={'background':'#048b8c'}),
                pn.pane.PNG(map_image, height=500, align='center'),
                # Bottom-right (key, map parameters).
                pn.Row(
                    pn.pane.PNG(key_image, height=200),
                    pn.Column(
                        pn.Param(scheduler,
                                  parameters=["survey_map","nside","color_palette"],
                                  name="Map, resolution, & color scheme.")
                        )
                    )
                )
            ),
        # Debugger.
        debug_info
        ).servable()
    
    # Copied from Eric's Prenight.py, but it doesn't work and I'm not sure what should be written instead.
    def clear_caches(session_context):
        logging.info("Session cleared.")
        sched_app.stop()                                                       # Doesn't work, no attribute stop()
    
    try:
        pn.state.on_session_destroyed(clear_caches)
    except RuntimeError as e:
        logging.info("RuntimeError: %s", e)

    return sched_app

    
if __name__ == "__main__":
    print("Starting scheduler dashboard.")

    if "SCHEDULER_PORT" in os.environ:
        scheduler_port = int(os.environ["SCHEDULER_PORT"])
    else:
        scheduler_port = 8080

    pn.serve(
        scheduler_app,
        port       = scheduler_port,
        title      = "Scheduler Dashboard",
        show       = True,
        start      = True,
        autoreload = True,
        threaded   = True,
    )
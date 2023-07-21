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
import schedview.plot.survey

"""
Notes
-----
    
    - Syntax, naming conventions, formatting, etc., mostly follows Eric's
      prenight.py.


Still to implement
------------------
    
    1. Survey/basis function holoviz map.
    2. Link basis_function selection and map selection to plot display.
    3. Link nside drop down selection to map nside.
    4. Link color palette drop down selection to map color palette.
    5. Check if able to load pickle from a URL.
    6. Make a key from bokeh.


Current issues
--------------
    
    Map display:
        - I have created a map following prenight.py but it loads blank.
        - This could be due to not having the PREOPS3512 branch of schedview.
    
    Logo:
        - Row/column layout: there is an unexplainable gap on the right
                             side of the Rubin logo.
        - GridSpec layout:   logo aligned correctly.
    
    Debugger/error log options:
        a) Debugger: unsightly and the messages (all levels) are useless.
        b) Terminal: slightly less unsightly and useful errors
        c) Custom debugger: pretty, customisable, but text won't stay in box.
    
    Layout options:
        - Row/column: all rows/columns are equally divided.
        - GridSpec:   custom spacing but tables overrun their space.


Pending questions
-----------------
    
    - Are users choosing a date or a datetime?

"""

DEFAULT_TIMEZONE        = "Chile/Continental"
DEFAULT_CURRENT_TIME    = Time.now()
DEFAULT_SCHEDULER_FNAME = "scheduler.pickle.xz"

color_palettes = [s for s in bokeh.palettes.__palettes__ if "256" in s]

LOGO      = "/Users/me/Documents/2023/ADACS/Panel_scheduler/Rubin_scheduler_dashboard/lsst_white_logo.png"
key_image = "/Users/me/Documents/2023/ADACS/Panel_scheduler/Rubin_scheduler_dashboard/key_image.png"
map_image = "/Users/me/Documents/2023/ADACS/Panel_scheduler/Rubin_scheduler_dashboard/map_image.png" # Temporary, until map can be displayed.

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

terminal = pn.widgets.Terminal(height=100, sizing_mode='stretch_width')




class Scheduler(param.Parameterized):
    
    scheduler_fname = param.String(default="",
                                   label="Scheduler pickle file")
    date            = param.Date(DEFAULT_CURRENT_TIME.datetime.date())
    tier            = param.ObjectSelector(default="", objects=[""])
    survey          = param.Integer(default=-1)
    basis_function  = param.Integer(default=-1)
    survey_map      = param.ObjectSelector(default="", objects=[""])
    plot_display    = param.Integer(default=1)
    nside           = param.ObjectSelector(default="16",
                                           objects=["8","16","32"],
                                           label="Map resolution (nside)")
    color_palette   = param.ObjectSelector(default="Magma256",
                                           objects=color_palettes)
    debug_string    = param.String(default="")

    _scheduler                = param.Parameter(None)
    _conditions               = param.Parameter(None)
    _date_time                = param.Parameter(None)
    _rewards                  = param.Parameter(None)                          # not used in @depends method
    _survey_rewards           = param.Parameter(None)
    _listed_survey            = param.Parameter(None)
    _survey_maps              = param.Parameter(None)
    _tier_survey_rewards      = param.Parameter(None)
    _basis_functions          = param.Parameter(None)
    _survey_df_widget         = param.Parameter(None)
    _basis_function_df_widget = param.Parameter(None)
    _debugging_message        = param.Parameter(None)
    
    
    # Dashboard headings ------------------------------------------------------# Should these functions be below others?
    
    # Panel for dashboard title.
    @param.depends("tier", "survey", "plot_display", "survey_map", "basis_function")
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
                                                           'font-weight':'bold'})
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
    @param.depends("survey", "plot_display", "survey_map", "basis_function")
    def map_title(self):
        if self._scheduler is not None and self.survey >= 0:
            titleA = 'Survey {}\n'.format(self._tier_survey_rewards.reset_index()['survey_name'][self.survey])
            if self.plot_display == 1:
                titleB = 'Map {}'.format(self.survey_map)
            elif self.plot_display == 2 and self.basis_function >= 0:
                titleB = 'Basis function {}: {}'.format(self.basis_function,
                                                        self._basis_functions['basis_function'][self.basis_function])
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
            self._debugging_message = f"Could not load scheduler from {self.scheduler_fname}: {e}"
            terminal.write(f"\n {Time.now().iso} - Could not load scheduler from {self.scheduler_fname}: {e}")
    
    
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
            self._rewards  = self._scheduler.make_reward_df(self._conditions)
            survey_rewards = schedview.compute.scheduler.make_scheduler_summary_df(self._scheduler,
                                                                                   self._conditions,
                                                                                   self._rewards)
            self._survey_rewards = survey_rewards
        except Exception as e:
            logging.error(e)
            logging.info("Survey rewards table unable to be updated. Perhaps date not in range of pickle data?")
            self._debugging_message = "Survey rewards table unable to be updated: " + str(e)
            terminal.write(f"\n {Time.now().iso} - Survey rewards table unable to be updated: {e}")
            self._survey_rewards = None


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
            self._debugging_message = "Survey rewards unable to be updated: " + str(e)
            terminal.write(f"\n {Time.now().iso} - Survey rewards unable to be updated: {e}")
            self._tier_survey_rewards = None


    # Widget for survey reward table.
    @param.depends("_tier_survey_rewards")
    def survey_rewards_table(self):
        if self._tier_survey_rewards is None:
            return "No surveys available."
        tabulator_formatter = {'survey_name': {'type': 'link',
                                                'labelField':'survey_name',
                                                'urlField':'survey_url',
                                                'target':'_blank'}}
        survey_rewards_table = pn.widgets.Tabulator(self._tier_survey_rewards[['tier','survey_name','reward','survey_url']],
                                                    widths={'survey_name':'60%','reward':'40%'},
                                                    show_index=False,
                                                    formatters=tabulator_formatter,
                                                    disabled=True,
                                                    selectable=1,
                                                    hidden_columns=['tier','survey_url'],
                                                    #height=200,
                                                    sizing_mode='stretch_width',
                                                    #sizing_mode='stretch_both',
                                                    )
        logging.info("Finished updating survey rewards table.")
        self._survey_df_widget = survey_rewards_table
        return survey_rewards_table


    # Update selected survey based on row selection of survey_rewards_table.
    @param.depends("_survey_df_widget.selection", watch=True)
    def update_survey_with_row_selection(self):
        logging.info("Updating survey row selection.")
        if self._survey_df_widget.selection == []:
            self.survey = -1
            return
        try:
            self.survey = self._survey_df_widget.selection[0]
        except Exception as e:
            logging.error(e)
            self._debugging_message = "Survey selection unable to be updated: " + str(e)
            terminal.write(f"\n {Time.now().iso} - Survey selection unable to be updated: {e}")
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
            self._debugging_message = "Listed survey unable to be updated: " + str(e)
            terminal.write(f"\n {Time.now().iso} - Listed survey unable to be updated: {e}")
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
                                                                  nside=8)    # Change once nside selector is made.
                                                                  #nside=nside)
        maps = list(self._survey_maps.keys())
        self.param["survey_map"].objects = maps
        if 'reward' in maps:                                                   # If 'reward' map always exists, then this isn't needed.
            self.survey_map = maps[-1]                                         # Reward map usually (always?) listed last.
        else:
            self.survey_map = maps[0]
        self.plot_display = 1


    # Update the parameter which determines whether a basis function or a map is plotted.
    @param.depends("survey_map", watch=True)
    def _update_plot_display(self):
        logging.info("Updating parameter for basis/map display.")
        #self.plot_display = 1                                                  # Display map instead of basis function.
        if self.survey_map != "":
            self.plot_display = 1


    # Update basis function table if new survey chosen.
    @param.depends("_listed_survey", "survey_rewards_table", watch=True)
    def _update_basis_functions(self):
        if self._listed_survey is None:
            return
        logging.info("Updating basis function table.")
        try:
            tier_id = int(self.tier[-1])
            survey_id = self.survey
            basis_function_df = schedview.compute.survey.make_survey_reward_df(self._listed_survey,
                                                                               self._conditions,
                                                                               self._rewards.loc[[(tier_id, survey_id)], :])
            self._basis_functions = basis_function_df
        except Exception as e:
            logging.error(e)
            self._debugging_message = "Basis function dataframe unable to be updated: " + str(e)
            terminal.write(f"\n {Time.now().iso} - Basis function dataframe unable to be updated: {e}")
            self._basis_functions = None


    # Widget for basis function table.
    @param.depends("_basis_functions")
    def basis_function_table(self):
        if self._basis_functions is None:
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
                                                    frozen_columns=['basis_function'],
                                                    hidden_columns=['doc_url'],
                                                    selectable=1,
                                                    #height=500,
                                                    #sizing_mode='stretch_both',
                                                    )
        self._basis_function_df_widget = basis_function_table
        return basis_function_table


    # Update selected basis_function based on row selection of basis_function_table.
    @param.depends("_basis_function_df_widget.selection", watch=True)
    def update_basis_function_with_row_selection(self):
        if self._basis_function_df_widget.selection == []:
            return
        logging.info("Updating basis function row selection.")
        try:
            self.plot_display = 2                                              # Display basis function instead of a map.
            self.basis_function = self._basis_function_df_widget.selection[0]
        except Exception as e:
            logging.error(e)
            self._debugging_message = "Basis function dataframe selection unable to be updated: " + str(e)
            terminal.write(f"\n {Time.now().iso} - Basis function dataframe selection unable to be updated: {e}")
            self.basis_function = -1                                           # When no basis function selected, basis_function = -1.


    # Create sky_map of survey for display (DISPLAYING WHITE SPACE!)
    @param.depends("_conditions","_survey_maps")
    def sky_map(self):
        if self._conditions is None:
            return "No scheduler loaded."
        if self._survey_maps is None:
            return "No surveys are loaded."
        try:
            sky_map = schedview.plot.survey.map_survey_healpix(60158.125,#self._conditions.mjd,
                                                               self._survey_maps,
                                                               "reward",
                                                               8)
                                                               #self.survey_map,
                                                               #self.nside)
            logging.info("Map successfully created.")
        except Exception as e:
            logging.info("Could not load map ...")
            logging.error(e)
            logging.info("... due to above reason.")
            self._debugging_message = "Could not load map: " + str(e)
            terminal.write(f"\n {Time.now().iso} - Could not load map: {e}")
            return "No map loaded."
        
        return sky_map
    

    # Panel for debugging messages
    @param.depends("_debugging_message")
    def debugging_messages(self):
        if self._debugging_message is None:
            return
        self.debug_string += f"\n {Time.now().iso} - {self._debugging_message}"
        debugging_messages = pn.pane.Str(self.debug_string,
                                         height=80,
                                         #width=800,
                                         #sizing_mode='stretch_width',
                                         styles={'font-size':'9pt',
                                                 'color':'black'})
        return debugging_messages
    

def scheduler_app(date=None, scheduler_pickle=None):
    
    scheduler = Scheduler()
    
    if date is not None:
        scheduler.date = date
    
    if scheduler_pickle is not None:
        scheduler.scheduler_fname = scheduler_pickle
    
   
        # Debugger. - (3 options)
        
        # OPTION 1
        # debug_info
        
        # OPTION 2
        # pn.Row(
        #     pn.Spacer(width=10),
        #     pn.Column(
        #         pn.pane.Str(' Debugging', align='center', styles={'font-size':'10pt','color':'black'}),
        #         terminal,
        #         styles={'background':'#EDEDED'}),
        #     pn.Spacer(width=10))
        
        # OPTION 3
        # pn.Column(pn.pane.Str(' Debugging', styles={'font-size':'10pt','font-weight':'bold','color':'black'}),
        #           scheduler.debugging_messages,
        #           #pn.layout.HSpacer(),
        #           sizing_mode='stretch_width',
        #           width_policy='max',
        #           height=100,
        #           styles={'background':'#EDEDED'})

    
    sched_app = pn.GridSpec(sizing_mode='stretch_both', max_height=1000).servable()
    
    # Dashboard title.
    sched_app[0,    :]    = pn.Row(scheduler.dashboard_title,
                                   pn.layout.HSpacer(),
                                   pn.pane.PNG(LOGO,
                                               sizing_mode='scale_height',
                                               align='center', margin=(5,5,5,5)),
                                   sizing_mode='stretch_width',
                                   styles={'background':'#048b8c'})
    # Parameter inputs (pickle, date, tier)
    sched_app[1:4,  0:3]  = pn.Param(scheduler,
                                     parameters=["scheduler_fname","date","tier"],
                                     widgets={'scheduler_fname':{'widget_type':pn.widgets.TextInput,
                                                                 'placeholder':'filepath or URL of pickle'},
                                              'date':pn.widgets.DatetimePicker},
                                     name="Select pickle file, date and tier.")
    # Survey rewards table and header.
    sched_app[1:4,  3:8]  = pn.Row(pn.Spacer(width=10),
                                   pn.Column(pn.Spacer(height=10),
                                      pn.Row(scheduler.survey_rewards_title,
                                             styles={'background':'#048b8c'}),
                                      pn.param.ParamMethod(scheduler.survey_rewards_table, loading_indicator=True)),
                                   pn.Spacer(width=10),
                                   #height=200,
                                   sizing_mode='stretch_height')
    # Basis function table and header.
    sched_app[4:11, 0:8]  = pn.Row(pn.Spacer(width=10),
                                   pn.Column(pn.Spacer(height=10),
                                      pn.Row(scheduler.basis_function_table_title,
                                             styles={'background':'#048b8c'}),
                                      pn.param.ParamMethod(scheduler.basis_function_table, loading_indicator=True)),
                                   pn.Spacer(width=10))
    # Map display and header.
    sched_app[1:8,  8:12] = pn.Column(pn.Spacer(height=10),
                                      pn.Row(scheduler.map_title,styles={'background':'#048b8c'}),
                                      pn.pane.PNG(map_image, sizing_mode='scale_both', align='center'))
    # Map display parameters (map, nside, color palette)
    sched_app[8:11, 8:12] = pn.Row(pn.pane.PNG(key_image, height=200),
                                   pn.Column(pn.Param(scheduler,
                                                      parameters=["survey_map","nside","color_palette"],
                                                      show_name=False)))
    # Debugging pane.
    sched_app[11,   :]    = pn.Row(pn.Spacer(width=10),
                                   pn.Column(pn.pane.Str(' Debugging',
                                                         align='center',
                                                         styles={'font-size':'10pt','color':'black'}),
                                             terminal,
                                             styles={'background':'#EDEDED'}),
                                   pn.Spacer(width=10))

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
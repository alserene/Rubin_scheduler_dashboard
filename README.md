# Rubin scheduler dashboard.

This is an in-progress prototype for the Rubin Observatory's scheduler dashboard.

Currently, the survey, basis function and map data loads and is able to be selected from the tables; however, the display of a HorizonMap of a selected basis function/map has not yet been implemented. Until this is made functional, a static map is displayed in place of the HorizonMap.

# Requirements.

* Host a copy of [schedview](https://github.com/lsst/schedview/tree/main) in a virtual environment on your local machine (following the instructions given in the schedview README.md).
* Generate a scheduler pickle file from [schedview scheduler notebook](https://github.com/lsst/schedview/blob/8f958ba623ce3c89c59a91b61222c19d33bac581/notebooks/scheduler.ipynb).
* Make the required modification to your local schedview code base specified in the below section, [Schedview compute_maps edit](#schedview-compute_maps-edit).
* In the dashboard script, modify the file paths for the three images used in the dashboard to reference where they are saved on your local machine.

# Running the dashboard.

At your command line, activate your virtual environment and run the following command:

    $ python <file-path-to-dashboard-script>

Once the dashboard has loaded in a web browser, enter the file path to your generated scheduler pickle file in the scheduler fname text input box, and select an appropriate datetime (e.g. the same datetime used to generate the pickle file).

# Schedview `compute_maps` edit

There is a numpy command in the `compute_maps` function in [schedview.compute.survey](https://github.com/lsst/schedview/blob/8f958ba623ce3c89c59a91b61222c19d33bac581/schedview/compute/survey.py) that errors when a map is being computed for a survey with an infeasible reward.

To fix this error, line 131 must be slightly modified as follows:

| Code version | Code |
| --- | --- |
| Old | values = np.fill(np.empty(hp.nside2npix(nside)), values) |
| New | values = np.full(np.shape(np.empty(hp.nside2npix(nside))), -np.inf) |

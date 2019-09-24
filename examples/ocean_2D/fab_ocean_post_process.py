import numpy as np
import easyvvuq as uq
import os
import fabsim3_cmd_api as fab
import matplotlib.pyplot as plt
from scipy import stats

def get_kde(X, Npoints = 100):

    kernel = stats.gaussian_kde(X)
    x = np.linspace(np.min(X), np.max(X), Npoints)
    pde = kernel.evaluate(x)
    return x, pde

#post processing of UQ samples executed via FabSim. All samples must have been completed
#before this subroutine is executed. Use 'fabsim <machine_name> job_stat' to check their status
def post_proc(state_file, work_dir):
    
    #Reload the campaign
    my_campaign = uq.Campaign(state_file = state_file, work_dir = work_dir)

    print('========================================================')
    print('Reloaded campaign', my_campaign.campaign_dir.split('/')[-1])
    print('========================================================')
    
    #get sampler and output columns from my_campaign object
    my_sampler = my_campaign._active_sampler
    output_columns = my_campaign._active_app_decoder.output_columns
    
    #fetch the results from the (remote) host via FabSim3
    #get_UQ_results(my_campaign.campaign_dir, machine='eagle_vecma')
    fab.get_uq_samples(my_campaign.campaign_dir, machine='localhost')

    #collate output
    my_campaign.collate()

    # Post-processing analysis
    sc_analysis = uq.analysis.SCAnalysis(sampler=my_sampler, qoi_cols=output_columns)
    my_campaign.apply_analysis(sc_analysis)
    results = my_campaign.get_last_analysis()
    results['n_samples'] = sc_analysis._number_of_samples
    
#    #store data
#    store_uq_results(my_campaign.campaign_dir, results)

    return results, sc_analysis, my_sampler, my_campaign

if __name__ == "__main__":
    
    #home dir of this file    
    HOME = os.path.abspath(os.path.dirname(__file__))

    work_dir = "/tmp"

    results, sc_analysis, my_sampler, my_campaign = post_proc(state_file="campaign_state_test.json", work_dir = work_dir)

    print('========================================================')
    print('Sobol indices E:')
    print(results['sobols']['E_mean'])
    print('========================================================')

    #################################
    # Use SC expansion as surrogate #
    #################################
    
    #number of MC samples
    n_mc = 50000
    
    fig = plt.figure()
    ax = fig.add_subplot(111, xlabel=r'$E$', yticks = [])
    
    #get the input distributions
    theta = my_sampler.vary.get_values()
    xi = np.zeros([n_mc, 2])
    idx = 0
    
    #draw random sampler from the input distributions
    for theta_i in theta:
        xi[:, idx] = theta_i.sample(n_mc)
        idx += 1
        
    #evaluate the surrogate at the random values
    Q = 'E_mean'
    qoi = np.zeros(n_mc)
    for i in range(n_mc):
        qoi[i] = sc_analysis.surrogate(Q, xi[i])
        
    #plot kernel density estimate of surrogate samples
    x, kde = get_kde(qoi)
    plt.plot(x, kde, label=r'$\mathrm{Energy\;pdf}$')
    plt.legend()
    plt.tight_layout()
    
plt.show()
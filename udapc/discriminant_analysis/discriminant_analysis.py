# Standard library imports
import os 
import sys
import time 

# Make sure python version is >= 3.6
if sys.version_info < (3, 6):
    raise ImportError("Python < 3.6 is not supported!")

# Third-party imports
import numpy as np
import pandas as pd
import random
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import silhouette_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix
from sklearn.metrics import accuracy_score
from scipy.spatial import ConvexHull

# Custom imports
from udapc.dim_reduction.dim_reduction import DimReduction
from udapc.utils.misc import progressbar
from udapc.utils.misc import timer
from udapc.utils.misc import isnotebook
from udapc.discriminant_analysis import unlda

is_notebook = isnotebook()

if is_notebook:
    from tqdm.notebook import tqdm as progressbar
else:
    from tqdm import tqdm as progressbar

class DiscriminantAnalysis(DimReduction):
    """[Class to perform supervised discriminant analysis of pricipal components (DAPC) or discriminant analysis of other embeddings]

    Args
        ([DimReduction]): [Inherits from DimReduction]
    """

    def __init__(
        self, 
        embedding, 
        *,
        run_xval=False,
        n_pca_min=10,
        n_pca_iter=10,
        n_pca_max=300,
        n_pca=None,
        n_da=None, 
        dimreduction=None, 
        pops=None,
        sampleids=None,
        prefix=None, 
        scale=False,
        colors=None, 
        palette="Set1", 
        maxk=8, 
        training_set=0.8,
        solver="eigen",
        init="heuristic", 
        classifier=None,
        lda_kwargs=dict(),
        xval_reps=30, 
        reps=1,
        test_classify=True,
        random_state=0,
        xval_global=False,
        max_reps=300,
        xval_metric="rmse"
    ):
        """[Run DAPC. The embedding object is required. Either a DimReduction object or each of the gt, pops, sampleids, prefix, reps, and [colors or palette] objects are also required.]

        Args:
            embedding ([runPCA, runMDS, or runTSNE object]): [Embedded data object created by runPCA(), runMDS(), or runTSNE()]

            dimreduction (DimReduction object, optional): [Initialized DimReduction object. If not supplied, gt, pops, sampleids, prefix, reps, colors, and palette must be supplied instead]. Defaults to None.

            pops (list(str), optional): [List of populations created by GenotypeData of shape (n_samples,). Can be retrieved as GenotypeData.populations]. Defaults to None.

            prefix ([str], optional): [Prefix for outptut files and plots]. Defaults to None.

            reps ([int], optional): [Number of replicates to perform]. Defaults to None.

            scaler (str, optional): [Scaler to use for genotype data. Valid options include "patterson", "standard", and "center". "patterson" follows a Patterson standardization (Patterson, Price & Reich (2006)) recommended for genetic data that scales the data to unit variance at each SNP. "standard" does regular standardization to unit variance and centers the data. "center" does not do a standardization and just centers the data]. Defaults to "patterson".

            colors ([dict(str)], optional): [Dictionary with unique populations IDs as the keys and hex-code colors as the values. If None, then uses the matplotlib palette supplied to palette]. Defaults to None.

            palette (str, optional): [matplotlib color palette to use if colors=None]. Defaults to "Set1".

            maxk (int, optional): [Highest K value to test]. Defaults to 8.

            sampleids ([list(str)], optional): [Sample IDs to write to labels files of shape (n_samples,). Can be retrieved as GenotypeData.individuals]. Defaults to None.

            metric (str, optional): [What distance metric to use for clustering. See sklearn.metrics.pairwise_distances documentation. If distances is not None, metric is ignored]. Defaults to "euclidean".

            init (str, optional): [Specify medoids initialization method. Supported options include "heuristic", "random", "k-medoids++", and "build". See sklearn_extra.cluster.KMedoids documentation]. Defaults to "heuristic".

            max_iter (int, optional): [Specify the maximum number of iterations when fitting. See sklearn_extra.cluster.KMedoids documentation]. Defaults to 300.

            random_state ([int], optional): [Specify random state for the random number generator. Used to initialize medoids when init="random". See sklearn_extra.cluster.KMedoids documentation]. Defaults to None.
        """
        # Initialize parent class
        super().__init__(gt=None, pops=pops, sampleids=sampleids, prefix=prefix, scaler="None", colors=colors, palette=palette)

        # Validates passed arguments and sets parent class attributes
        #self._validate_args(dimreduction, pops, sampleids, prefix, reps, scaler)

        # Set child class attributes
        self.embedding = embedding
        self.use_embedding = True
        self.maxk = maxk
        
        self.init = init
        self.reps = reps
        self.xval_reps=xval_reps
        self.max_reps=max_reps
        self.random_state = random_state
        
        self.training_set = training_set
        self.run_xval = run_xval
        self.n_pca_min = n_pca_min
        self.n_pca_iter = n_pca_iter
        self.n_pca_max = n_pca_max
        self.n_pca = n_pca
        self.n_da = n_da
        self.scale = scale
        self.solver = solver
        self.test_classify = test_classify
        self.classifier=classifier
        self.lda_kwargs=lda_kwargs
        self.xval_global=xval_global

        # To store results
        self.labels = list()
        self.models = list()
        self.pred_labels = list()
        self.X = None
        self.xval_metric=xval_metric

        # Get attributes from already instantiated embedding
        #self.coords = embedding.coords
        #self.method = embedding.method

        # Do cluster analysis from embedding
        self.fit_predict()
        

    @timer
    def fit_predict(self):
        """[Fit model and predict cluster labels. Sets self.labels (predicted labels) and self.models (fit model). self.labels and self.models are lists of dictionaries. Each list item corresponds to one replicate, and each dictionary has k values as the keys and the labels and models as values]

        Args:
            X ([pandas.DataFrame or numpy.ndarray]): [Coordinates following dimensionality reduction embedding of shape (n_samples, n_features) or distance matrix of shape (n_samples, n_samples). Accessed via self.coords]
        """
        print("\nPerforming Discriminant Analysis...\n")
            
                    
        if self.pops is not None:
            print(
                "Supervised DAPC Settings:\n"
                    "\tsolver: "+str(self.solver)+"\n"
                    "\trun_xval: "+str(self.run_xval)+"\n"
                    "\txval_reps: "+str(self.xval_reps)+"\n"
                    "\trandom_state: "+str(self.random_state)+"\n"
            )
            self.method = "supervised DAPC"
            num_samples = len(self.embedding.coords[0])
            labels=self.pops
            test_size = 1.0-self.training_set
            n_components = self.n_da
            if n_components is None:
                n_components = len(set(labels))-1
    
            #make training and test datasets

            #X_train, X_test, y_train, y_test = train_test_split(variables, labels, test_size=test_size, random_state=self.random_state)
            
            #build kwargs for LDA 
            params = {
                'solver' : self.solver
            }
            for key in self.lda_kwargs:
                params[key] = self.lda_kwargs[key]
            
            
            #run cross-validation procedure to select n_pca
            pca_reps = range(self.n_pca_min, self.n_pca_max, self.n_pca_iter)
            if self.run_xval:
                print("\nRunning cross-validation...\n")
                props=dict()
                for rep in progressbar(
                    pca_reps, 
                    desc="Xval iteration: ", 
                    leave=True, 
                    position=0):
                    
                    _X = list()
                    
                    for samp in self.embedding.coords[0]:
                        _X.append(samp[0:rep])
                    if self.scale:
                        _X = StandardScaler().fit_transform(_X)
                    
                    for k in progressbar(
                        range(1, self.xval_reps+1), 
                        desc="Replicates: ", 
                        leave=False, 
                        position=1):
                        
                        #subset training and test data
                        _X_train, _X_test, _label_train, _label_test = train_test_split(_X, labels, test_size=test_size, random_state=self.random_state+random.randint(0,10000))
                        
                        #Run DAPC on training data 
                        _clf = LinearDiscriminantAnalysis()
                        _clf.set_params(**params)
                        _clf.fit(_X_train, _label_train)
                        _coords_train = _clf.transform(_X_train)
                        _coords_test = _clf.transform(_X_test)

                        #get classifications for test data (after placing in DA ordination space)
                        if self.classifier is None:
                            _label_pred = _clf.predict(_X_test)
                        else:
                            self.classifier.fit(_coords_train, _labels_train)
                            _label_pred = self.classifier.predict(_X_test)
                        
                        #get classification accuracy score
                        if self.xval_global:
                            accuracy = accuracy_score(_label_test, _label_pred, normalize=True)
                        else:
                            accuracies=list()
                            for pop in set(_label_test):
                                _idx = [i for i,e in enumerate(_label_test) if e==pop]
                                _t = [_label_test[i] for i in _idx]
                                _p = [_label_pred[i] for i in _idx]
                                accuracies.append(accuracy_score(_t, _p, normalize=True))
                            accuracy = sum(accuracies)/len(accuracies)
                        
                        #add to list of accuracies for later calculating MSE
                        if rep not in props:
                            props[rep] = list()
                        props[rep].append(accuracy)
                df = pd.DataFrame.from_dict(props)
                df.index.name = 'rep'
                df.reset_index(inplace=True)
                melted = pd.melt(df, id_vars=['rep'], var_name='PCs', value_name='accuracy')
                
                self.plot_xval_accuracy(melted)
                
                rmse = dict()
                min_rmse=None
                best_pc_rmse=None
                max_mae=None
                best_pc_mae=None
                for key in props:
                    mae=sum([e for e in props[key]])/len(props[key])
                    s=sum([e-1 for e in props[key]])
                    ss=s*s
                    mse=ss/len(props[key])
                    rmse[key] = np.sqrt(mse)
                    if max_mae is None:
                        max_mae = mae
                        best_pc_mae = key
                    else:
                        if mae > max_mae:
                            max_mae = mae
                            best_pc_mae = key
                        elif max_mae == mae:
                            best_pc_mae = max(key, best_pc_mae)
                            
                    if min_rmse is None:
                        min_rmse = rmse[key]
                        best_pc_rmse = key
                    else:
                        if rmse[key] < min_rmse:
                            min_rmse = rmse[key]
                            best_pc_rmse = key
                        elif rmse[key] == min_rmse:
                            best_pc_rmse = min(key, best_pc_rmse)
                d=dict()
                d["PCs"]=list(rmse.keys())
                d["RMSE"]=list(rmse.values())
                #print(d)
                dfr = pd.DataFrame.from_dict(d)
                #print(dfr)
                self.plot_xval_rmse(dfr)
                
                if self.xval_metric == "mae" or self.xval_metric == "MAE":
                    print("Number PCs minimizing mean absolute error (MAE):", best_pc_mae)
                    self.n_pca = best_pc_mae
                else:
                    print("Number PCs minimizing root-mean-square-error (RMSE):", best_pc_rmse)
                    self.n_pca = best_pc_rmse


            #select PCs to run full DAPC 
            if self.n_pca is None:
                self.n_pca = len(self.embedding.coords[0][0])
            variables = list()
            for samp in self.embedding.coords[0]:
                variables.append(samp[0:self.n_pca])
            if self.scale:
                variables = StandardScaler().fit_transform(variables)
            #print(variables)
            
            #run LDA
            clf = LinearDiscriminantAnalysis()
            clf.set_params(**params)
            clf.fit(variables, labels)
            coords_all = clf.transform(variables)
            
            self.coords = [coords_all]
            return(coords_all)

class UnsupervisedDiscriminantAnalysis(DimReduction):
    """[Class to perform unsupervised discriminant analysis of pricipal components (DAPC) or discriminant analysis of other embeddings]

    Args
        ([DimReduction]): [Inherits from DimReduction]
    """

    def __init__(
        self, 
        embedding, 
        *,
        run_xval=False,
        n_pca_min=10,
        n_pca_iter=10,
        n_pca_max=300,
        n_pca=None,
        dimreduction=None, 
        pops=None,
        sampleids=None,
        prefix=None, 
        scale=False,
        colors=None, 
        palette="Set1", 
        maxk=8,
        fixedk=None,
        subset=1.0,
        lda_kwargs=dict(),
        reps=10,
        max_iter=300,
        center=True,
        tol=0.000001,
        gamma=0.000001,
        n_init=10,
        n_try=10
    ):
        """[Run DAPC. The embedding object is required. Either a DimReduction object or each of the gt, pops, sampleids, prefix, reps, and [colors or palette] objects are also required.]

        Args:
            embedding ([runPCA, runMDS, or runTSNE object]): [Embedded data object created by runPCA(), runMDS(), or runTSNE()]

            dimreduction (DimReduction object, optional): [Initialized DimReduction object. If not supplied, gt, pops, sampleids, prefix, reps, colors, and palette must be supplied instead]. Defaults to None.

            pops (list(str), optional): [List of populations created by GenotypeData of shape (n_samples,). Can be retrieved as GenotypeData.populations]. Defaults to None.

            prefix ([str], optional): [Prefix for outptut files and plots]. Defaults to None.

            reps ([int], optional): [Number of replicates to perform]. Defaults to None.

            subset (float, optional): [Specify proportion of data subsetted for hyperparameter optimization replicates]. Defaults to 1.0 (no subsetting)

            scaler (str, optional): [Scaler to use for genotype data. Valid options include "patterson", "standard", and "center". "patterson" follows a Patterson standardization (Patterson, Price & Reich (2006)) recommended for genetic data that scales the data to unit variance at each SNP. "standard" does regular standardization to unit variance and centers the data. "center" does not do a standardization and just centers the data]. Defaults to "patterson".

            colors ([dict(str)], optional): [Dictionary with unique populations IDs as the keys and hex-code colors as the values. If None, then uses the matplotlib palette supplied to palette]. Defaults to None.

            palette (str, optional): [matplotlib color palette to use if colors=None]. Defaults to "Set1".

            maxk (int, optional): [Highest K value to test]. Defaults to 8.

            fixedk (int, optional): [Fixed K value, setting this supercedes maxk and skips optimization for k]. Defaults to None.

            sampleids ([list(str)], optional): [Sample IDs to write to labels files of shape (n_samples,). Can be retrieved as GenotypeData.individuals]. Defaults to None.

            n_try (int, optional):[Number of tries for k-means clustering each iteration]. Defaults to 10. 

            n_init (int, optional):[Specify numbner ]. Defaults to 10. 

            max_iter (int, optional): [Specify the maximum number of iterations when fitting]. Defaults to 300.

            center (boolean, optional): [Specify whether input is centered in un_rtlda]. Defaults to True.

            tol (float, optional): [Specify absolute tolerance for fitting]. Defaults to 1e-6.

            gamma (float, optional): [Specify value of regularization term gamma]. Defaults to 1e-6.

        """
        # Initialize parent class
        super().__init__(gt=None, pops=pops, sampleids=sampleids, prefix=prefix, scaler="None", colors=colors, palette=palette)

        # Validates passed arguments and sets parent class attributes
        #self._validate_args(dimreduction, pops, sampleids, prefix, reps, scaler)

        # Set child class attributes
        self.embedding = embedding
        self.use_embedding = True
        self.maxk = maxk
        self.fixedk = fixedk
        
        self.n_init = n_init
        self.reps = reps
        self.max_iter = max_iter
        self.n_try = n_try
        self.subset = subset

        self.tol = tol 
        self.gamma = gamma
        self.center = center
        
        self.n_pca_min = n_pca_min
        self.n_pca_iter = n_pca_iter
        self.n_pca_max = n_pca_max
        self.n_pca = n_pca

        self.subset = subset

        # To store results
        self.labels = list()
        self.models = list()
        self.pred_labels = list()
        self.X = None

        # Get attributes from already instantiated embedding
        #self.coords = embedding.coords
        #self.method = embedding.method

        # Do cluster analysis from embedding
        self.fit_predict()

    @timer
    def fit_predict(self):
        """[Fit model and predict cluster labels. Sets self.labels (predicted labels) and self.models (fit model). self.labels and self.models are lists of dictionaries. Each list item corresponds to one replicate, and each dictionary has k values as the keys and the labels and models as values]

        Args:
            X ([pandas.DataFrame or numpy.ndarray]): [Coordinates following dimensionality reduction embedding of shape (n_samples, n_features) or distance matrix of shape (n_samples, n_samples). Accessed via self.coords]
        """
        print("\nPerforming Unsupervised Discriminant Analysis...\n")
        
        # embedding input matrix 
        input = np.array(self.embedding.coords[0])

        # check that self.n_pca_max doesn't exceed number of dimensions in input embedding 
        if self.n_pca_max > input.shape[1]:
            print("WARNING: n_pca_max exceeds number of dimensions in input embedding, setting n_pca_max to", str(input.shape[1]))
            self.n_pca_max = input.shape[1]

        # define number of values for grid search 
        if self.n_pca:
            pca_reps = self.n_pca 
        else:
            pca_reps = range(self.n_pca_min, self.n_pca_max, self.n_pca_iter)
        
        if self.fixedk:
            k_reps = self.fixedk
        else:
            #k_reps = range(2, self.maxk)
            k_reps = range(2, self.maxk)

        print(
            "Unsupervised DAPC Settings:\n"
                "\tsolver: Ratio-trace\n"
                "\treplicates: "+str(self.reps)+"\n"
                "\tnumber PC dimensions to test: "+str(len(pca_reps))+"\n"
                "\tnumber K values to test: "+str(len(k_reps))+"\n"
                "\tsubset: "+str(self.subset)+"\n"
        )
        self.method = "unsupervised DAPC"
        num_samples = len(self.embedding.coords[0])
        subset_samples = self.subset * num_samples

        # check if known labels are provided 
        if self.pops: 
            labels = self.pops 
        else:
            labels = None 
        #test_size = 1.0-self.training_set
        
        print("\nRunning optimization...\n")
        results = dict()
    
        for rep in progressbar(range(self.reps), desc="Replicates: ", leave=True, position=0):
            print(self.subset)
            if self.subset < 1.0:
                _subset = [random.sample(samp, subset_samples) for samp in self.embedding.coords[0]]
            else:
                _subset = self.embedding.coords[0].copy()

            results[rep] = dict()
            print(rep)
            for k in progressbar(k_reps, desc="K values: ", leave=False, position=1):
                objective_values = []
                print(k)
                print(_subset)
                for p in progressbar(pca_reps, desc="PC dimensions: ", leave=False, position=2):
                    _X = np.array([samp[0:p] for samp in _subset])
                    # Apply Un-RTLDA and obtain the reduced-dimensional representation and cluster assignments
                    print(rep, k, p)
                    T, G, W, obj = unlda.un_rtlda(_X, 
                            k, 
                            Ninit=self.n_init, 
                            max_iter=self.max_iter, 
                            Ntry=self.n_try, 
                            center=self.center, 
                            gamma=self.gamma, 
                            tol=self.tol,
                            no_pca=True)
                    silhouette = silhouette_score(T, G)
                    print(str(len(obj)), silhouette)
                    # Compute clustering performance metrics
                    #unlda.print_metrics(T, labels, G)

                    # Call plot_embeddings on simulated data
                    #unlda.plot_embeddings(T, G, W, _X, labels, k)
                    
                    #sys.exit()
        sys.exit()
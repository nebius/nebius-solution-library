/**
 * DataSelectionStep Component
 *
 * First step: Select training data source
 * - ChEMBL database search
 * - Upload custom CSV
 * - Demo datasets
 */

import { useState, useCallback } from 'react';
import { useFineTuning } from '../../../contexts/FineTuningContext';
import {
  searchTargets,
  getActivityCount,
  fetchActivityData,
  getDemoDataset,
  parseUploadedCsv,
  DEMO_DATASETS,
} from '../../../services/chemblApi';
import type { ChemBLTarget, DataSourceType } from '../../../types/finetuning';

export function DataSelectionStep() {
  const { setDataSource, setDataset, goToNextStep } = useFineTuning();

  // ChEMBL search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<ChemBLTarget[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<ChemBLTarget | null>(null);
  const [activityType, setActivityType] = useState<'IC50' | 'Ki' | 'EC50' | 'Kd'>('IC50');
  const [activityCount, setActivityCount] = useState<number | null>(null);
  const [isLoadingData, setIsLoadingData] = useState(false);

  // Upload state
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Selected source
  const [selectedSource, setSelectedSource] = useState<DataSourceType | null>(null);

  // Handle ChEMBL search
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) return;

    setIsSearching(true);
    setSearchResults([]);
    setSelectedTarget(null);

    try {
      const results = await searchTargets(searchQuery);
      setSearchResults(results);
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setIsSearching(false);
    }
  }, [searchQuery]);

  // Handle target selection
  const handleSelectTarget = useCallback(
    async (target: ChemBLTarget) => {
      setSelectedTarget(target);
      setActivityCount(null);

      try {
        const count = await getActivityCount(target.chemblId, activityType);
        setActivityCount(count);
      } catch (error) {
        console.error('Failed to get activity count:', error);
      }
    },
    [activityType]
  );

  // Load ChEMBL data
  const handleLoadChemblData = useCallback(async () => {
    if (!selectedTarget) return;

    setIsLoadingData(true);
    try {
      const dataset = await fetchActivityData(selectedTarget.chemblId, activityType);
      dataset.name = `${selectedTarget.name} ${activityType} Data`;
      setDataSource('chembl');
      setDataset(dataset);
      goToNextStep();
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setIsLoadingData(false);
    }
  }, [selectedTarget, activityType, setDataSource, setDataset, goToNextStep]);

  // Handle file upload
  const handleFileUpload = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;

      setUploadError(null);

      try {
        const content = await file.text();
        const dataset = parseUploadedCsv(content);
        dataset.name = file.name.replace(/\.[^/.]+$/, '');
        setDataSource('upload');
        setDataset(dataset);
        goToNextStep();
      } catch (error) {
        setUploadError(error instanceof Error ? error.message : 'Failed to parse file');
      }
    },
    [setDataSource, setDataset, goToNextStep]
  );

  // Handle demo dataset selection
  const handleSelectDemo = useCallback(
    (datasetId: string) => {
      const dataset = getDemoDataset(datasetId);
      setDataSource('demo');
      setDataset(dataset);
      goToNextStep();
    },
    [setDataSource, setDataset, goToNextStep]
  );

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Select Training Data</h1>
          <p className="content-subtitle">
            Choose a data source for fine-tuning your property prediction model.
          </p>
        </div>
      </div>

      {/* ChEMBL Search */}
      <div
        className={`card data-source-card ${selectedSource === 'chembl' ? 'selected' : ''}`}
        onClick={() => setSelectedSource('chembl')}
      >
        <div className="card-header">
          <div className="data-source-header">
            <div className="data-source-icon chembl">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
                <path d="M12 6v6l4 2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <h3 className="card-title">ChEMBL Database</h3>
              <p className="card-subtitle">Search millions of bioactivity measurements</p>
            </div>
          </div>
          <span className="card-badge">Recommended</span>
        </div>

        {selectedSource === 'chembl' && (
          <div className="card-body" onClick={(e) => e.stopPropagation()}>
            <div className="chembl-search">
              <div className="search-input-group">
                <input
                  type="text"
                  className="form-input"
                  placeholder='e.g., "COX-2", "CHEMBL220", "BCR-ABL"'
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                />
                <button
                  className="btn btn-primary"
                  onClick={handleSearch}
                  disabled={isSearching || !searchQuery.trim()}
                >
                  {isSearching ? (
                    <span className="spinner spinner-sm" />
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M11 11l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                  )}
                  Search
                </button>
              </div>

              {/* Search Results */}
              {searchResults.length > 0 && (
                <div className="search-results">
                  {searchResults.map((target) => (
                    <button
                      key={target.chemblId}
                      className={`search-result-item ${
                        selectedTarget?.chemblId === target.chemblId ? 'selected' : ''
                      }`}
                      onClick={() => handleSelectTarget(target)}
                    >
                      <div className="search-result-info">
                        <span className="search-result-name">{target.name}</span>
                        <span className="search-result-meta">
                          {target.chemblId} • {target.organism} • {target.targetType}
                        </span>
                      </div>
                      {selectedTarget?.chemblId === target.chemblId && (
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <path
                            d="M3 8l3 3 7-7"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </button>
                  ))}
                </div>
              )}

              {/* Activity Type & Load */}
              {selectedTarget && (
                <div className="chembl-load-options">
                  <div className="activity-type-selector">
                    <label className="form-label">Activity Type</label>
                    <div className="activity-type-buttons">
                      {(['IC50', 'Ki', 'EC50', 'Kd'] as const).map((type) => (
                        <button
                          key={type}
                          className={`activity-type-btn ${activityType === type ? 'active' : ''}`}
                          onClick={() => {
                            setActivityType(type);
                            getActivityCount(selectedTarget.chemblId, type).then(setActivityCount);
                          }}
                        >
                          {type}
                        </button>
                      ))}
                    </div>
                  </div>

                  {activityCount !== null && (
                    <div className="activity-count">
                      <span className="activity-count-number">{activityCount.toLocaleString()}</span>
                      <span className="activity-count-label">compounds available</span>
                    </div>
                  )}

                  <button
                    className="btn btn-primary btn-lg"
                    onClick={handleLoadChemblData}
                    disabled={isLoadingData || activityCount === 0}
                  >
                    {isLoadingData ? (
                      <>
                        <span className="spinner spinner-sm" />
                        Loading Data...
                      </>
                    ) : (
                      <>
                        Load Dataset
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <path
                            d="M6 12l4-4-4-4"
                            stroke="currentColor"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Upload CSV */}
      <div
        className={`card data-source-card ${selectedSource === 'upload' ? 'selected' : ''}`}
        onClick={() => setSelectedSource('upload')}
      >
        <div className="card-header">
          <div className="data-source-header">
            <div className="data-source-icon upload">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path
                  d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div>
              <h3 className="card-title">Upload Your Data</h3>
              <p className="card-subtitle">CSV file with SMILES and activity values</p>
            </div>
          </div>
        </div>

        {selectedSource === 'upload' && (
          <div className="card-body" onClick={(e) => e.stopPropagation()}>
            <div className="upload-area">
              <input
                type="file"
                accept=".csv"
                onChange={handleFileUpload}
                className="upload-input"
                id="csv-upload"
              />
              <label htmlFor="csv-upload" className="upload-label">
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                  <path
                    d="M28 20v5.333A2.667 2.667 0 0125.333 28H6.667A2.667 2.667 0 014 25.333V20M22.667 10.667L16 4l-6.667 6.667M16 4v16"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="upload-text">Drop CSV file here or click to browse</span>
                <span className="upload-hint">Format: smiles, activity (header required)</span>
              </label>
              {uploadError && <p className="upload-error">{uploadError}</p>}
            </div>
          </div>
        )}
      </div>

      {/* Demo Datasets */}
      <div
        className={`card data-source-card ${selectedSource === 'demo' ? 'selected' : ''}`}
        onClick={() => setSelectedSource('demo')}
      >
        <div className="card-header">
          <div className="data-source-header">
            <div className="data-source-icon demo">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <div>
              <h3 className="card-title">Demo Datasets</h3>
              <p className="card-subtitle">Pre-loaded datasets for quick testing</p>
            </div>
          </div>
        </div>

        {selectedSource === 'demo' && (
          <div className="card-body" onClick={(e) => e.stopPropagation()}>
            <div className="demo-datasets">
              {DEMO_DATASETS.map((demo) => (
                <button
                  key={demo.id}
                  className="demo-dataset-item"
                  onClick={() => handleSelectDemo(demo.id)}
                >
                  <div className="demo-dataset-info">
                    <span className="demo-dataset-name">{demo.name}</span>
                    <span className="demo-dataset-description">{demo.description}</span>
                  </div>
                  <div className="demo-dataset-meta">
                    <span className="demo-dataset-count">
                      {demo.compoundCount.toLocaleString()} compounds
                    </span>
                    <span className="demo-dataset-type">{demo.activityType}</span>
                  </div>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path
                      d="M6 12l4-4-4-4"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

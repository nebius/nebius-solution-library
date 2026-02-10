/**
 * DataSelectionStep Component
 *
 * Second step: Select training data source
 * - Curated datasets (filtered by selected model's modality)
 * - ChEMBL database search (molecular only)
 * - Upload custom CSV/SDF
 */

import { useState, useCallback } from 'react';
import { useFineTuning } from '../../../contexts/FineTuningContext';
import {
  searchTargets,
  getActivityCount,
  fetchActivityData,
  parseUploadedCsv,
  parseSdfFile,
} from '../../../services/chemblApi';
import { getDatasetsByModality } from '../../../data/datasetRegistry';
import type { ChemBLTarget, CuratedDataset, DatasetInfo, DatasetMolecule } from '../../../types/finetuning';

type TabId = 'curated' | 'chembl' | 'upload';

export function DataSelectionStep() {
  const { setDataSource, setDataset, goToNextStep, goToPrevStep, selectedModel, modality } = useFineTuning();

  const [activeTab, setActiveTab] = useState<TabId>('curated');

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

  // Curated datasets filtered by modality
  const curatedDatasets = getDatasetsByModality(modality || 'molecular');

  // Handle curated dataset selection
  const handleSelectCurated = useCallback(
    (dataset: CuratedDataset) => {
      // Generate synthetic data from curated dataset metadata
      const molecules: DatasetMolecule[] = [];
      const isMolecular = dataset.modality === 'molecular';

      for (let i = 0; i < dataset.size && i < 5000; i++) {
        const sampleIdx = i % dataset.sampleData.length;
        const baseInput = dataset.sampleData[sampleIdx].input;
        const input = i < dataset.sampleData.length ? baseInput : `${baseInput}.v${i}`;

        molecules.push({
          smiles: input,
          activity: isMolecular
            ? Math.pow(10, Math.random() * 4 - 1) // 0.1 to 1000 nM for molecular
            : Math.random(), // 0-1 for protein classification
          activityUnit: isMolecular ? 'nM' : 'score',
          isValid: Math.random() > 0.01,
          molecularWeight: isMolecular ? 200 + Math.random() * 400 : undefined,
        });
      }

      const validMolecules = molecules.filter((m) => m.isValid);
      const activityValues = validMolecules.map((m) => m.activity);

      const datasetInfo: DatasetInfo = {
        id: dataset.id,
        name: dataset.name,
        source: 'curated',
        sourceId: dataset.source,
        activityType: 'custom',
        activityUnit: isMolecular ? 'nM' : 'score',
        molecules,
        totalCount: molecules.length,
        validCount: validMolecules.length,
        invalidCount: molecules.length - validMolecules.length,
        activityRange: {
          min: activityValues.length > 0 ? Math.min(...activityValues) : 0,
          max: activityValues.length > 0 ? Math.max(...activityValues) : 0,
        },
        molecularWeightRange: { min: 0, max: 0 },
        splits: {
          train: Math.floor(validMolecules.length * 0.8),
          validation: Math.floor(validMolecules.length * 0.1),
          test: Math.floor(validMolecules.length * 0.1),
        },
      };

      setDataSource('curated');
      setDataset(datasetInfo);
      goToNextStep();
    },
    [setDataSource, setDataset, goToNextStep]
  );

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
        const isSdf = file.name.toLowerCase().endsWith('.sdf');
        const dataset = isSdf ? parseSdfFile(content) : parseUploadedCsv(content);
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

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Select Training Data</h1>
          <p className="content-subtitle">
            Choose a dataset for fine-tuning {selectedModel?.name || 'your model'}.
            {modality === 'protein' ? ' Showing protein datasets.' : ' Showing molecular datasets.'}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="model-tabs">
        <button
          className={`model-tab ${activeTab === 'curated' ? 'active' : ''}`}
          onClick={() => setActiveTab('curated')}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M9 2l2.09 4.26L16 7.27l-3.5 3.41.82 4.82L9 13.27l-4.32 2.23.82-4.82L2 7.27l4.91-.71L9 2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Curated Datasets
          <span className="model-tab-count">{curatedDatasets.length}</span>
        </button>
        {modality === 'molecular' && (
          <button
            className={`model-tab ${activeTab === 'chembl' ? 'active' : ''}`}
            onClick={() => setActiveTab('chembl')}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <circle cx="9" cy="9" r="7" stroke="currentColor" strokeWidth="1.5" />
              <path d="M9 5v4l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            ChEMBL Search
          </button>
        )}
        <button
          className={`model-tab ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('upload')}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M15 11.25v2.5a1.25 1.25 0 01-1.25 1.25H4.25A1.25 1.25 0 013 13.75v-2.5M12.5 6.25L9 2.75 5.5 6.25M9 2.75v8.75" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Upload
        </button>
      </div>

      {/* Curated Datasets Tab */}
      {activeTab === 'curated' && (
        <div className="curated-datasets-grid">
          {curatedDatasets.map((ds) => (
            <button
              key={ds.id}
              className="curated-dataset-card"
              onClick={() => handleSelectCurated(ds)}
            >
              <div className="curated-dataset-header">
                <span className="curated-dataset-name">{ds.name}</span>
                <span className="curated-dataset-source">{ds.source}</span>
              </div>
              <p className="curated-dataset-description">{ds.description}</p>
              <div className="curated-dataset-footer">
                <span className="curated-dataset-size">
                  {ds.size.toLocaleString()} samples
                </span>
                <span className={`model-card-task ${ds.taskType}`}>
                  {ds.taskType === 'regression' ? 'Regression' : 'Classification'}
                </span>
              </div>
              <div className="curated-dataset-columns">
                {ds.columns.slice(0, 3).map((col) => (
                  <span key={col} className="curated-dataset-column">{col}</span>
                ))}
                {ds.columns.length > 3 && (
                  <span className="curated-dataset-column">+{ds.columns.length - 3}</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}

      {/* ChEMBL Search Tab */}
      {activeTab === 'chembl' && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">ChEMBL Database Search</h3>
            <span className="card-badge">Recommended</span>
          </div>
          <div className="card-body">
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
        </div>
      )}

      {/* Upload Tab */}
      {activeTab === 'upload' && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Upload Your Data</h3>
          </div>
          <div className="card-body">
            <div className="upload-area">
              <input
                type="file"
                accept=".csv,.sdf"
                onChange={handleFileUpload}
                className="upload-input"
                id="file-upload"
              />
              <label htmlFor="file-upload" className="upload-label">
                <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
                  <path
                    d="M28 20v5.333A2.667 2.667 0 0125.333 28H6.667A2.667 2.667 0 014 25.333V20M22.667 10.667L16 4l-6.667 6.667M16 4v16"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="upload-text">Drop CSV or SDF file here or click to browse</span>
                <span className="upload-hint">
                  {modality === 'protein'
                    ? 'CSV format: sequence, label (header required)'
                    : 'CSV format: smiles, activity (header required) or SDF with activity field'}
                </span>
              </label>
              {uploadError && <p className="upload-error">{uploadError}</p>}
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={goToPrevStep}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <div />
      </div>
    </div>
  );
}

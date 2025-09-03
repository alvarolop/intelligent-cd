from kfp import dsl
from kfp import compiler
from kfp import kubernetes
from kfp.client import Client

from llama_stack_client import LlamaStackClient
from llama_stack_client import RAGDocument

import os

@dsl.component(base_image="python:3.13")
def create_urls_list() -> list:
    """Creates a list of document URLs."""
    urls = [
        "01-intro.md",
        "02-deployment-constraints.md",
        "03-network-security.md",
        "04-routing-loadbalancing.md",
        "05-storage-architecture.md",
        "06-resource-monitoring.md",
        "07-deployment-procedures.md"
    ]
    
    # Return the URLs list directly
    return urls

@dsl.component(base_image="python:3.13", packages_to_install=["llama-stack-client"])
def download_documents(document_urls: list) -> list:
    """Downloads the documents."""
    
    from llama_stack_client import RAGDocument
    
    # The input contains the URLs list directly
    urls = document_urls
    
    document_base_url = "https://raw.githubusercontent.com/alvarolop/intelligent-cd/refs/heads/main/intelligent-cd-docs"
    
    documents = []
    for url in urls:
        doc = RAGDocument(
            document_id=f"{url}",
            content=f"{document_base_url}/{url}",
            mime_type="text/plain",
            metadata={
                "source": "https://github.com/alvarolop/intelligent-cd/tree/main/intelligent-cd-docs",
                "url": f"{document_base_url}/{url}",
                "title": url,
                "date": "2025-09-01"
            },
        )
        documents.append(doc)
    
    # Return the documents list directly
    return documents

@dsl.component(base_image="python:3.13", packages_to_install=["llama-stack-client"])
def ingest_documents(documents: list) -> None:
    """Ingest the documents into the vector database."""
    
    from llama_stack_client import LlamaStackClient
    import os
    
    # The input contains the documents list directly
    # documents is a list of dictionaries with document data    
    # print(f"Documents to ingest: {documents}")
    
    # Process each document
    for doc in documents:
        print(f"Processing document: {doc['document_id']}")
        print(f"Content: {doc['content']}")
        print(f"Metadata: {doc['metadata']}")
    
    # Initialize client
    client = LlamaStackClient(
        base_url=os.getenv("LLAMA_STACK_URL"),
        # timeout=httpx.Timeout(120.0, read=5.0, write=10.0, connect=2.0)
        timeout=180.0 # 3 minutes
    )
    
    vector_db_id = os.getenv("VECTOR_DB_ID")
    
    # Check if vector database exists, create if it doesn't
    try:
        # Try to get the vector database to check if it exists
        client.vector_dbs.retrieve(vector_db_id=vector_db_id)
        print(f"Vector database '{vector_db_id}' already exists")
    except Exception as e:
        print(f"Vector database '{vector_db_id}' does not exist, creating it...")
        print(f"Error: {e}")
        
        # Create the vector database
        client.vector_dbs.register(
            vector_db_id=vector_db_id,
            embedding_model="granite-embedding-125m",
            embedding_dimension=768,
            provider_id="milvus"
        )
        print(f"Vector database '{vector_db_id}' created successfully")
    
    # Now insert the documents
    client.tool_runtime.rag_tool.insert(
        documents=documents,
        vector_db_id=vector_db_id,
        chunk_size_in_tokens=512,
    )

@dsl.pipeline(name="ingest-pipeline")
def pipeline():
    
    # Step 1: Create the URLs list
    urls = create_urls_list()
    
    # Step 2: Download the documents
    documents = download_documents(document_urls=urls.output)
    
    # Step 3: Ingest the documents with secrets handling
    step3 = ingest_documents(documents=documents.output)

    kubernetes.use_secret_as_env(
        step3,
        secret_name='ingestion-secret',
        secret_key_to_env={
            'LLAMA_STACK_URL': 'LLAMA_STACK_URL',
            'VECTOR_DB_ID': 'VECTOR_DB_ID'
        })

# Helper function to get or create pipeline
def get_or_create_pipeline(client, pipeline_name, package_path):
    """Get existing pipeline or create new one."""
    existing_pipelines = client.list_pipelines()
    
    # Check if pipelines list exists and has items
    if existing_pipelines and hasattr(existing_pipelines, "pipelines") and existing_pipelines.pipelines:
        for pipeline in existing_pipelines.pipelines:
            if pipeline.display_name == pipeline_name:
                print(f"Pipeline '{pipeline_name}' already exists with ID: {pipeline.pipeline_id}")
                return pipeline
    
    # Pipeline doesn't exist, create it
    print(f"Pipeline '{pipeline_name}' not found, uploading new pipeline...")
    pipeline_obj = client.upload_pipeline(
        pipeline_package_path=package_path,
        pipeline_name=pipeline_name
    )
    print(f"Pipeline uploaded successfully with ID: {pipeline_obj.pipeline_id}")
    return pipeline_obj

# Helper function to get or create experiment
def get_or_create_experiment(client, experiment_name, description):
    """Get existing experiment or create new one."""
    existing_experiments = client.list_experiments()
    
    # Check if experiments list exists and has items
    if existing_experiments and hasattr(existing_experiments, "experiments"):
        for exp in existing_experiments.experiments:
            if exp.display_name == experiment_name:
                print(f"Experiment '{experiment_name}' already exists with ID: {exp.experiment_id}")
                return exp
    
    # Experiment doesn't exist, create it
    print(f"Experiment '{experiment_name}' not found, creating new experiment...")
    experiment = client.create_experiment(
        name=experiment_name,
        description=description
    )
    print(f"Experiment created successfully with ID: {experiment.experiment_id}")
    return experiment

# Helper function to check if run exists and execute if needed
def execute_pipeline_if_needed(client, experiment, pipeline_obj, run_name):
    """Check if run exists and execute pipeline if needed."""
    existing_runs = client.list_runs(experiment_id=experiment.experiment_id)
    
    # Check if runs list exists and has items
    if existing_runs and hasattr(existing_runs, "runs") and existing_runs.runs:
        for run in existing_runs.runs:
            if run.display_name == run_name:
                print(f"Run '{run_name}' already exists with ID: {run.run_id}")
                print("Skipping pipeline execution to avoid duplicates.")
                return run
    
    # Run doesn't exist, execute pipeline
    print("Starting new pipeline execution...")
    
    # First, retrieve the first version of the pipeline
    pipeline_versions = client.list_pipeline_versions(pipeline_id=pipeline_obj.pipeline_id)
    if pipeline_versions and hasattr(pipeline_versions, "pipeline_versions") and pipeline_versions.pipeline_versions:
        # Just get the first version from the array
        version_id = pipeline_versions.pipeline_versions[0].pipeline_version_id
        print(f"Using pipeline version: {version_id}")
    else:
        raise RuntimeError("No versions found for the pipeline to execute.")
    
    # Then, run the pipeline with the retrieved version
    run_result = client.run_pipeline(
        experiment_id=experiment.experiment_id,
        job_name=run_name,
        pipeline_id=pipeline_obj.pipeline_id,
        version_id=version_id
    )
    print(f"Pipeline execution started with run ID: {run_result.run_id}")
    return run_result

if __name__ == "__main__":
    # SVC: https://ds-pipeline-dspa.{namespace}.svc:8443
    # Route: https://ds-pipeline-dspa-rhoai-playground.apps.$CLUSTER_DOMAIN
    kubeflow_endpoint = os.environ["KUBEFLOW_ENDPOINT"]
    bearer_token = os.environ["BEARER_TOKEN"]

    # 1. Create KFP client
    print(f'Connecting to Data Science Pipelines: {kubeflow_endpoint}')
    kfp_client = Client(
        host=kubeflow_endpoint,
        existing_token=bearer_token
    )

    # 2. Create pipeline object
    pipeline_package = compiler.Compiler().compile(
        pipeline_func=pipeline,
        package_path="ingest-pipeline.yaml"
    )

    # 3. Get or create pipeline
    pipeline_obj = get_or_create_pipeline(kfp_client, "ingest-pipeline", "ingest-pipeline.yaml")
    print(f"Pipeline ready with ID: {pipeline_obj.pipeline_id}")

    # 4. Get or create experiment
    experiment = get_or_create_experiment(
        kfp_client, 
        "ingest-experiment", 
        "Runs our pipeline to ingest documents into the vector database"
    )
    print(f"Experiment ready with ID: {experiment.experiment_id}")

    # 5. Execute pipeline if needed
    run_result = execute_pipeline_if_needed(kfp_client, experiment, pipeline_obj, "ingest-execution") 

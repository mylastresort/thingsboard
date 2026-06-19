async def sync_parameters(
    model_path: Optional[str] = Query(
        None, description="Single model name or absolute path to a .fsm file."
    ),
    model_paths: Optional[list[str]] = Query(
        None, description="List of model names or absolute paths to sync."
    ),
    evaluation_license: bool = Query(
        default=True,
        description="Use evaluation license mode when auto-launching FlexSim.",
    ),
    session: FlexSimSession = Depends(get_flexsim_session),
):
    print(
        f"Received sync parameters request with model_path={model_path}, model_paths={model_paths}"
    )
    model_targets = _resolve_sync_model_targets(model_path, model_paths)
    return await sync_model_parameters_from_thingsboard(
        session=session,
        model_paths=model_targets,
        evaluation_license=evaluation_license,
    )


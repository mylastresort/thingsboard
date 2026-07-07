package org.tb.quarkus.cli;

import io.quarkus.picocli.runtime.annotations.TopCommand;
import picocli.CommandLine;

@TopCommand
@CommandLine.Command(
        name = "aob-tb-loader",
        mixinStandardHelpOptions = true,
        version = "1.0.0",
        subcommands = { PullPushCommand.class, TestConnectionCommand.class },
        description = "Loads IBM Research's AssetOpsBench scenarios from HuggingFace into a ThingsBoard CE instance."
)
public class Main implements Runnable {
    @Override
    public void run() {
        System.out.println("Run with a subcommand, e.g.: aob-tb-loader pull-push --dry-run");
    }
}

package org.tb.quarkus.pdm;

import jakarta.enterprise.context.ApplicationScoped;
import org.apache.avro.Schema;

import java.io.InputStream;

@ApplicationScoped
public class PdmAvroSchemas {

    private final Schema command = load("/avro/pdm-commands-value.avsc");
    private final Schema jobState = load("/avro/pdm-job-state-value.avsc");

    public Schema command() {
        return command;
    }

    public Schema jobState() {
        return jobState;
    }

    private Schema load(String resource) {
        try (InputStream input = getClass().getResourceAsStream(resource)) {
            if (input == null) {
                throw new IllegalStateException("Missing Avro schema resource: " + resource);
            }
            return new Schema.Parser().parse(input);
        } catch (Exception e) {
            throw new IllegalStateException("Failed to load Avro schema: " + resource, e);
        }
    }
}

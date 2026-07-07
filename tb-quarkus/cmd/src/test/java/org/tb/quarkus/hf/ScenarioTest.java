package org.tb.quarkus.hf;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

class ScenarioTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void deserializesStringId() throws Exception {
        Scenario scenario = mapper.readValue("""
                {
                  "id": "pdm_rul_001",
                  "utterance": "predict remaining useful life"
                }
                """, Scenario.class);

        assertEquals("pdm_rul_001", scenario.id);
    }

    @Test
    void deserializesNumericIdAsText() throws Exception {
        Scenario scenario = mapper.readValue("""
                {
                  "id": 42,
                  "utterance": "download Chiller 6 tonnage"
                }
                """, Scenario.class);

        assertEquals("42", scenario.id);
    }
}

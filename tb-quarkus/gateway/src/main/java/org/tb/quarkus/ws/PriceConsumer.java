package org.tb.quarkus.ws;

import jakarta.enterprise.context.ApplicationScoped;
import org.eclipse.microprofile.reactive.messaging.Incoming;
import org.jboss.logging.Logger;

@ApplicationScoped
public class PriceConsumer {

    private static final Logger LOG = Logger.getLogger(PriceConsumer.class);

    @Incoming("prices")
    public void consume(double price) {
        LOG.info("Received price: " + price);
    }
}
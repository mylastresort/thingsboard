package groovy.scenario

class AssetProfileBuilder {
    String name
    String type = 'DEFAULT'
    String label
    Map<String, Object> attributes = [:]
    List<Map<String, String>> relations = []

    AssetProfileBuilder name(String name) { this.name = name; return this }
    AssetProfileBuilder type(String type) { this.type = type; return this }
    AssetProfileBuilder label(String label) { this.label = label; return this }
    AssetProfileBuilder attribute(String key, Object value) { attributes[key] = value; return this }
    AssetProfileBuilder attributes(Map<String, Object> attrs) { attributes.putAll(attrs); return this }

    AssetProfileBuilder relation(String entityType, String entityName, String relationType) {
        relations.add([entityType: entityType, entityName: entityName, type: relationType])
        return this
    }

    Map<String, Object> build() {
        [
            name      : name,
            type      : type,
            label     : label ?: name,
            attributes: attributes,
            relations : relations,
        ]
    }
}

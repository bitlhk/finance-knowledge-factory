package probe;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.flowable.dmn.api.DmnDecision;
import org.flowable.dmn.api.DmnDeployment;
import org.flowable.dmn.engine.DmnEngine;
import org.flowable.dmn.engine.DmnEngineConfiguration;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.HexFormat;
import java.security.MessageDigest;


public final class FlowableProbe {
    private record Installed(String key, String parent, String deployment, String definition) {}

    private static void verifyModel(Map<String, Object> model) throws Exception {
        Map<String, Object> content = new LinkedHashMap<>(model);
        String expected = (String) content.remove("compiledDigest");
        byte[] canonical = new ObjectMapper().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS).writeValueAsBytes(content);
        String actual = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(canonical));
        if (!actual.equals(expected)) throw new IllegalArgumentException("COMPILED_DIGEST_MISMATCH");
    }

    private static Installed install(DmnEngine engine, String key, String parent, String xml) {
        if (xml.contains("<!DOCTYPE") || xml.contains("<!ENTITY")) {
            throw new IllegalArgumentException("Unsafe XML rejected before deployment");
        }
        if (engine.getDmnRepositoryService().createDecisionQuery().parentDeploymentId(parent).count() != 0) {
            throw new IllegalArgumentException("Parent deployment identity must be unique");
        }
        DmnDeployment dep = engine.getDmnRepositoryService().createDeployment()
                .name("isolated-m1-probe").parentDeploymentId(parent).addString("rule.dmn", xml).deploy();
        DmnDecision decision = engine.getDmnRepositoryService().createDecisionQuery()
                .deploymentId(dep.getId()).decisionKey(key).singleResult();
        if (decision == null) throw new IllegalStateException("Definition missing");
        return new Installed(key, parent, dep.getId(), decision.getId());
    }

    private static Map<String, Object> execute(DmnEngine engine, Installed installed, Map<String, Object> vars) {
        var found = engine.getDmnRepositoryService().createDecisionQuery()
                .decisionKey(installed.key()).parentDeploymentId(installed.parent()).singleResult();
        if (found == null || !found.getId().equals(installed.definition())) {
            throw new IllegalStateException("Pinned definition changed");
        }
        List<Map<String, Object>> rows = engine.getDmnDecisionService().createExecuteDecisionBuilder()
                .decisionKey(installed.key()).parentDeploymentId(installed.parent()).variables(vars).executeDecision();
        if (rows.size() != 1 || !rows.getFirst().containsKey("decision")) {
            throw new IllegalStateException("Expected exactly one result");
        }
        return rows.getFirst();
    }

    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws Exception {
        ObjectMapper json = new ObjectMapper();
        Map<String, Object> input = json.readValue(Path.of(args[0]).toFile(), new TypeReference<>() {});
        DmnEngineConfiguration config = DmnEngineConfiguration.createStandaloneInMemDmnEngineConfiguration();
        config.setJdbcUrl("jdbc:h2:mem:knowledge_m1;DB_CLOSE_DELAY=-1");
        config.setDatabaseSchemaUpdate("true");
        config.setEnableSafeDmnXml(true);
        config.setCreateDiagramOnDeploy(false);
        DmnEngine engine = config.buildDmnEngine();
        Map<String, Object> report = new LinkedHashMap<>();
        List<Map<String, Object>> results = new ArrayList<>();
        int calls = 0;
        try {
            Map<String, Installed> installed = new LinkedHashMap<>();
            for (Map<String, Object> model : (List<Map<String, Object>>) input.get("models")) {
                verifyModel(model);
                String sha = (String) model.get("compiledDigest");
                installed.put(sha, install(engine, (String) model.get("key"), sha, (String) model.get("xml")));
            }
            for (Map<String, Object> row : (List<Map<String, Object>>) input.get("cases")) {
                Map<String, Object> result = new LinkedHashMap<>();
                result.put("id", row.get("id"));
                if (row.containsKey("guard")) {
                    result.put("actual", row.get("guard"));
                    result.put("executor", "INPUT_SCOPE_GUARD");
                } else {
                    Installed pin = installed.get(row.get("compiledDigest"));
                    calls++;
                    try {
                        result.put("actual", execute(engine, pin, (Map<String, Object>) row.get("variables")).get("decision"));
                        result.put("executor", "FLOWABLE_DMN_8.0.0");
                    } catch (RuntimeException error) {
                        result.put("actual", "ENGINE_ERROR");
                        result.put("errorType", error.getClass().getName());
                        result.put("error", error.getMessage());
                    }
                    result.put("definitionId", pin.definition());
                    result.put("deploymentId", pin.deployment());
                    result.put("parentDeploymentId", pin.parent());
                }
                result.put("expected", row.get("expected"));
                result.put("passed", row.get("expected").equals(result.get("actual")));
                results.add(result);
            }
            report.put("engine", "org.flowable:flowable-dmn-engine:8.0.0");
            report.put("engineCalls", calls);
            report.put("results", results);
            report.put("referenceFallback", false);
            List<Map<String, Object>> faultResults = new ArrayList<>();
            for (Map<String, Object> fault : (List<Map<String, Object>>) input.get("faults")) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("id", fault.get("id"));
                item.put("stage", "DEPLOYMENT");
                try {
                    Installed bad = install(engine, (String) fault.get("key"), "fault-" + fault.get("id"), (String) fault.get("xml"));
                    item.put("stage", "EXECUTION");
                    execute(engine, bad, (Map<String, Object>) fault.get("variables"));
                    item.put("rejected", false);
                } catch (RuntimeException error) {
                    item.put("rejected", true);
                    item.put("errorType", error.getClass().getName());
                    item.put("error", error.getMessage());
                }
                faultResults.add(item);
            }
            Installed first = installed.values().iterator().next();
            try {
                execute(engine, new Installed(first.key(), "missing-version", first.deployment(), first.definition()), Map.of());
                faultResults.add(Map.of("id", "missing-pinned-version", "rejected", false));
            } catch (IllegalStateException error) {
                faultResults.add(Map.of("id", "missing-pinned-version", "rejected", true, "error", error.getMessage()));
            }
            Map<String, Object> corrupt = new LinkedHashMap<>(((List<Map<String, Object>>) input.get("models")).getFirst());
            corrupt.put("xml", corrupt.get("xml") + " ");
            try {
                verifyModel(corrupt);
                faultResults.add(Map.of("id", "tampered-artifact", "rejected", false));
            } catch (IllegalArgumentException error) {
                faultResults.add(Map.of("id", "tampered-artifact", "rejected", true, "error", error.getMessage()));
            }
            Map<String, Object> recovery = ((List<Map<String, Object>>) input.get("cases")).stream()
                    .filter(row -> !row.containsKey("guard") && "MET".equals(row.get("expected"))).findFirst().orElse(null);
            report.put("faultResults", faultResults);
            if (recovery == null) {
                report.put("sameEngineRecovery", null);
                report.put("recoveryStatus", "NOT_EXECUTED_NO_ELIGIBLE_CASE");
            } else {
                String restored = (String) execute(engine, installed.get(recovery.get("compiledDigest")),
                        (Map<String, Object>) recovery.get("variables")).get("decision");
                report.put("sameEngineRecovery", "MET".equals(restored));
                report.put("recoveryStatus", "EXECUTED");
            }
        } finally {
            engine.close();
        }
        Files.writeString(Path.of(args[1]), json.writerWithDefaultPrettyPrinter().writeValueAsString(report));
        if (results.stream().anyMatch(row -> !Boolean.TRUE.equals(row.get("passed")))) {
            throw new IllegalStateException("Probe has failures; inspect saved results");
        }
        if (((List<Map<String, Object>>) report.get("faultResults")).stream().anyMatch(row -> !Boolean.TRUE.equals(row.get("rejected")))
                || Boolean.FALSE.equals(report.get("sameEngineRecovery"))) {
            throw new IllegalStateException("Fault/recovery checks failed");
        }
    }
}

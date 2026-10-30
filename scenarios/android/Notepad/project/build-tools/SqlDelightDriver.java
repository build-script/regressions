import com.squareup.sqldelight.core.SqlDelightEnvironment;
import com.squareup.sqldelight.gradle.SqlDelightCompilationUnitImpl;
import com.squareup.sqldelight.gradle.SqlDelightDatabasePropertiesImpl;
import com.squareup.sqldelight.gradle.SqlDelightSourceFolderImpl;
import java.io.File;
import java.util.List;

/**
 * Runs the compiler inside SQLDelight's Gradle plugin the way its GenerateInterfaces
 * task does, SQLDelight 1.x has no command line of its own.
 * Arguments: package, class name, source directory, output directory, project directory.
 */
public final class SqlDelightDriver {
    public static void main(String[] args) {
        File source = new File(args[2]);
        File output = new File(args[3]);
        SqlDelightCompilationUnitImpl unit = new SqlDelightCompilationUnitImpl(
            "main", List.of(new SqlDelightSourceFolderImpl(source, false)), output);
        SqlDelightDatabasePropertiesImpl properties = new SqlDelightDatabasePropertiesImpl(
            args[0], List.of(unit), args[1], List.of(), "SQLITE_3_18", false, new File(args[4]));
        SqlDelightEnvironment environment = new SqlDelightEnvironment(properties, unit, false, "main", List.of(source), List.of());

        SqlDelightEnvironment.CompilationStatus status = environment.generateSqlDelightFiles(message -> kotlin.Unit.INSTANCE);
        if (status instanceof SqlDelightEnvironment.CompilationStatus.Failure) {
            for (String error : ((SqlDelightEnvironment.CompilationStatus.Failure) status).getErrors()) {
                System.err.println(error);
            }
            System.exit(1);
        }
    }
}

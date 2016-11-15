setwd('/Users/hills/Desktop/hillz/images/art/sharpie/')
files = system('ls', intern=T )
files = files[grepl(files, pattern='.J', fixed=T)]
for(file in files){
  system(paste0('mv ', file, ' ', sub(x = file, '.JPG', '.jpg')))
}